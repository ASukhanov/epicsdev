"""Helper functions for creating EPICS PVAccess server"""
# pylint: disable=invalid-name
__version__= 'v3.3.0 26-05-13'# Do not publish PV in its setter.
#TODO: Add CBOR-encoded PVs representing arbitrary Python objects, that can be used for storing complex data structures, such as dictionaries, numpy arrays. That will be more efficient than using multiple PVs for each parameter, and more flexible than using JSON-encoded strings.

import sys
import time
from time import perf_counter as timer
from datetime import datetime
import os
import json
import threading
from socket import gethostname
import numpy as np
import psutil
import p4p.nt
from p4p.server import Server
from p4p.server.thread import SharedPV
from p4p.client.thread import Context

#``````````````````Constants
PeriodicUpdateInterval = 10. # seconds
AutosaveInterval = 60. # seconds, interval for saving PV values to a file for autosave feature.
AutosaveDefaultDirectory = '/operations/app_store/pvCache/' # Fallback autosave directory when OPERATIONS is not set.
IFace = Context('pva')# client context for getting values from other servers

epics2p4p = {# mapping from epics type codes to p4p type codes.
's8':'b', 'u8':'B', 's16':'h', 'u16':'H', 'i32':'i', 'u32':'I', 'i64':'l',
'u64':'L', 'f32':'f', 'f64':'d', str:'s',
}
dtype2p4p = {# mapping from numpy dtype to p4p type code
np.dtype('int8'):'b', np.dtype('uint8') :'B',
np.dtype('int16'):'h', np.dtype('uint16'):'H', np.dtype('int32'):'i',
np.dtype('uint32'):'I', np.dtype('int64'):'l', np.dtype('uint64'):'L',
np.dtype('float32'):'f', np.dtype('float64'):'d'}

#``````````````````Module Storage`````````````````````````````````````````````
def _serverStateChanged(newState:str):
    """Dummy serverStateChanged function"""
    return

class C_():
    """Storage for module members"""
    prefix = ''
    verbose = 0
    startTime = 0.
    cycle = 0
    serverState = ''
    PVs = {}
    PVDefs = [] 
    serverStateChanged = _serverStateChanged
    lastCycleTime = timer()
    lastUpdateTime = 0.
    cycleTimeSum = 0.
    cyclesAfterUpdate = 0
    cachefd = None
    lastPutTime = time.time()# last time when a put operation was performed.
    lastAutosaveTime = 0.# last time when the cache was saved to a file.
    putlogPV = None # name of the PV where put operations are logged. If None, then put operations are not logged.

#```````````````````Helper methods````````````````````````````````````````````
def serverState():
    """Return current server state. That is the value of the server PV, but
    cached in C_ to avoid unnecessary get() calls."""
    return C_.serverState
def _printTime():
    return time.strftime("%m%d:%H%M%S")
def printi(msg):
    """Print info message and publish it to status PV."""
    print(f'inf_@{_printTime()}: {msg}')
def printw(msg):
    """Print warning message and publish it to status PV."""
    txt = f'WAR_@{_printTime()}: {msg}'
    print(txt)
    publish('status',txt)
def printe(msg):
    """Print error message and publish it to status PV."""
    txt = f'ERR_{_printTime()}: {msg}'
    print(txt)
    publish('status',txt)
def _printv(msg, level):
    if C_.verbose >= level: 
        print(f'DBG{level}: {msg}')
def printv(msg):
    """Print debug message if verbosity level >=1."""
    _printv(msg, 1)
def printvv(msg):
    """Print debug message if verbosity level >=2."""
    _printv(msg, 2)
def printv3(msg):
    """Print debug message if verbosity level >=3."""
    _printv(msg, 3)

def pvobj(pvName):
    """Return PV with given name"""
    return C_.PVs[C_.prefix+pvName]

def pvv(pvName:str):
    """Return PV value"""
    return pvobj(pvName).current()

def publish(pvName:str, value, ifChanged=False, t=None):
    """Publish value to PV. If ifChanged is True, then publish only if the 
    value is different from the current value. If t is not None, then use
    it as timestamp, otherwise use current time."""
    #print(f'Publishing {pvName} = {value}')
    try:
        pv = pvobj(pvName)
    except KeyError:
        print(f'WARNING: PV {pvName} not found. Cannot publish value.')
        return
    if t is None:
        t = time.time()
    if not ifChanged or pv.current() != value:
        pv.post(value, timestamp=t)

def write_cache():
    """Write PV values to the cache file. That will be used for autosave."""
    printv('Saving PV values to cache')
    pvcacheMap = {}
    for pvName, pv in C_.PVs.items():
        if pv.writable:
            value = pv._wrap(pv.current())['value']
            if isinstance(value, str):
                pyval = value
            else:
                # for discrete PVs, we need to save the index of the current choice, not the choice itself, because the choices can be changed in the next startup. That is a good example of using extra parameters in PV definitions.
                try:
                    pyval = value.index
                except Exception:
                    pyval = value
            #print(f'Caching {pvName} = {value} of type {type(value)}, python value: {pyval} of type {type(pyval)}')
            pvcacheMap[pvName[len(C_.prefix):]] = {'value': pyval, 'time': time.time()}
    #print(f'pvCache: {pvcacheMap}')
    C_.cachefd.seek(0)
    json.dump(pvcacheMap, C_.cachefd)
    C_.cachefd.truncate()
    C_.cachefd.flush()

#``````````````````create_PVs()```````````````````````````````````````````````

def create_PVs(pvDefs, pvcache=None):
    """Create PVs from the definitions in pvDefs."""
    if pvcache is None:
        pvcache = {}

    ts = time.time()
    for defs in pvDefs:
        try:
            pname,desc,initial,*extra = defs
        except ValueError:
            printe(f'Invalid PV definition of {defs[0]}')
            sys.exit(1)
        extra = extra[0] if extra else {}

        # Check the validity of PV definition and prepare parameters for creating PV.
        iterable  = type(initial) not in (int,float,str)
        allowed_chars = 'WRAD'
        meta = extra.get('features','')
        writable = 'W' in meta
        valueAlarm = extra.get('valueAlarm')
        ntextra = [('features', p4p.nt.Type([('writable', '?')]))]
        for ch in meta:
            if ch not in allowed_chars:
                printe(f'Unknown meta character {ch} in SPV definition')
                sys.exit(1)

        # Create PV. For multi-dimensional arrays, we always create NTNDArray,
        # that is the most flexible type, and supports all features.
        # For other types, we create NTEnum for discrete PVs, and NTScalar
        # or NTScalarArray for other PVs, depending on whether the initial 
        # value is iterable or not.
        if isinstance(initial, np.ndarray):# Multi-dimensional array.
            printv(f'Creating NTNDArray PV {pname}, initial: {initial}')
            #TODO:ISSUE:spv = SharedPV(nt=p4p.nt.NTNDArray(display=True))# do not use initial here due to a bug in p4p, also display keyword is not handled.
            spv = SharedPV(nt=p4p.nt.NTNDArray())
            spv.open(initial)
            spv.post(initial, timestamp=ts)

        else:# NtEnum or Scalar or 1D array.
            if 'D' in meta:# discrete PV, that is a PV with a list of choices.
                #The value of the PV is one of the choices.
                initial = {'choices': initial, 'index': 0}
                nt = p4p.nt.NTEnum(display=True, extra=ntextra)
            else:
                # NTScalar or NTScalarArray, depending on whether initial value is iterable or not.
                # The type is determined from the initial value, but it can be overridden by extra['type'].
                vtype = extra.get('type')
                if vtype is None:
                    firstItem = initial[0] if iterable else initial
                    itype = type(firstItem)
                    vtype = {int:'i32', float:'f32'}.get(itype,itype)
                tcode = epics2p4p[vtype]
                prefix = 'a' if iterable else ''
                nt = p4p.nt.NTScalar(prefix+tcode, display=True, control=writable,
                            valueAlarm = valueAlarm is not None, extra=ntextra)

            # If the PV value is cached in pvcache, then use the cached value as initial value.
            # That allows to restore PV values after server restart.
            if pname in pvcache:
                cached = pvcache[pname]['value']
                if isinstance(initial, dict):
                    initial['index'] = cached
                else:
                    initial = cached
                #printi(f'Loaded initial value for {pname} from autosave: {initial}')
            printv(f'Creating PV {pname}, initial: {initial}')
            spv = SharedPV(nt=nt, initial=initial)

            # Set initial value and description and add to the map of PVs
            ivalue = spv.current()
            ntNamedTuples = spv._wrap(ivalue, timestamp=ts)
            ntNamedTuples['display.description'] = desc
            ntNamedTuples['features.writable'] = writable

            # set extra parameters
            for field in extra.keys():
                try:
                    if field in ['limitLow','limitHigh','format','units']:
                        ntNamedTuples[f'display.{field}'] = extra[field]
                        if field.startswith('limit'):
                            ntNamedTuples[f'control.{field}'] = extra[field]
                    if field == 'valueAlarm':
                        for key,value in extra[field].items():
                            ntNamedTuples[f'valueAlarm.{key}'] = value
                except  KeyError as e:
                    print(f'ERROR. Cannot set {field} for {pname}: {e}')
                    sys.exit(1)
            spv.post(ntNamedTuples)
        printv((f'created pv {pname}, initial: {type(ivalue),ivalue},'
            f'extra: {extra}'))
        key = C_.prefix + pname
        if key in C_.PVs:
            printe(f'Duplicate PV name: {pname}')
            sys.exit(1)
        C_.PVs[C_.prefix+pname] = spv

        spv.writable = writable

        if writable:
            # add new attributes, that will be used in the put handler
            spv.name = pname
            spv.setter = extra.get('setter')

            # add a put handler to the PV, that will be called when the PV 
            # value is changed by a client. The handler will check limits, 
            # call the setter if defined, and update subscribers.
            @spv.put
            def handle(spv, op):
                vv = op.value()
                vr = vv.raw.value
                ntNamedTuples = spv._wrap(spv.current())
                oldvr = ntNamedTuples['value']
                try: # if it is ENum
                    index = oldvr.index
                    oldvr = oldvr.choices[index]
                except: pass
                #printv(f'oldvr: {type(oldvr)},{oldvr}')

                # check limits, if they are defined.
                try:
                    limitLow = ntNamedTuples['control.limitLow']
                    limitHigh = ntNamedTuples['control.limitHigh']
                    if limitLow != limitHigh and not (limitLow <= vr <= limitHigh):
                        printw(f'Value {vr} is out of limits [{limitLow}, {limitHigh}]. Ignoring.')
                        op.done(error=f'Value out of limits [{limitLow}, {limitHigh}]')
                        return
                except KeyError:
                    pass
                if isinstance(vv, p4p.nt.enum.ntenum):
                    vr = str(vv)
                if spv.setter:
                    spv.setter(vr, spv)
                #printv(f'putting {spv.name} = {type(vr)} {vr}')
                ct = time.time()
                C_.lastPutTime = ct
                spv.post(vr, timestamp=ct) # update subscribers

                #printv(f'putlog {spv.name} = {type(vr)} {vr}')
                if C_.putlogPV is not None:
                    dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3].split()
                    ip = op.peer().split(':')[3][:-1]# peer looks like: [::ffff:192.168.27.6]:46362
                    jmsg = {"date":dt[0], "time":dt[1], 
                        "host":ip, "user":op.account(),
                        "pv":op.name(), "new":vr, "old":oldvr}
                    s = json.dumps(jmsg)
                    try:
                        IFace.put(C_.putlogPV, "'"+s+"'", timeout=0.5)# quote the string to avoid interpreting it as JSON
                    except TimeoutError:
                        printw(f'WARNING: caPutLog feature will be disabled: PV {C_.putlogPV} not accessible.')
                        C_.putlogPV = None
                op.done()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Setters
def set_verbose(level, *_):
    """Set verbosity level for debugging"""
    C_.verbose = level
    printi(f'Setting verbose to {level}')

def set_server(servState, *_):
    """Example of the setter for the server PV.
    servState can be 'Start', 'Stop', 'Exit' or 'Clear'. If servState is None,
    then get the desired state from the server PV."""
    #printv(f'>set_server({servState}), {type(servState)}')
    if servState is None:
        servState = pvv('server')
        printi(f'Setting server state to {servState}')
    servState = str(servState)
    C_.serverStateChanged(servState)
    if servState == 'Start':
        printi('Starting the server')
        publish('status','Started')
    elif servState == 'Stop':
        printi('server stopped')
        publish('status','Stopped')
    elif servState == 'Exit':
        printi('server is exiting')
        publish('status','Exited')
    elif servState == 'Clear':
        publish('status','Cleared')
        set_server(C_.serverState)
        return
    C_.serverState = servState

def create_pvDefs(pvDefs=None, pvcache=None):
    """Create PVs from the definitions in pvDefs and return them as a dictionary.
    pvDefs is a list of PV definitions. Each definition is a list of 3 or 4 items:
    [pvName, description, initialValue, extraParameters]
    extraParameters is a dictionary with optional keys:
        'features': string with characters W (writable), D (discrete). For example. By default, PV is read-only scalar.
        'type': string with data type, for example 'f32', 'i32', 's8', etc. By default, the type is determined from the initial value (float -> 'f32', int -> 'i32').
        'units': string with physical units, for example 'V', 'S', 'Mpts/s', etc.
        'limitLow': number with low limit for the value. If defined, then the put handler will check that the value is not below the low limit.
        'limitHigh': number with high limit for the value. If defined, then the put handler will check that the value is not above the high limit.
        'setter': function to be called when the PV value is changed. The function should have the signature:
            def setter(value, spv):
            where value is the new value, and spv is the SharedPV object.
        The PVs defined in C_.PVDefs are created first, then the PVs from pvDefs are
        created and appended to the map of PVs. That allows to have some common PVs 
        defined in C_.PVDefs, and device-specific PVs defined in pvDefs.
    pvcache is a dictionary with initial values for PVs. It is used for autosave.
    The function returns a dictionary with PVs, where the keys are PV names and the values are SharedPV objects.
    """
    F,T,U,LL,LH = 'features','type','units','limitLow','limitHigh'
    C_.PVDefs = [

# Mandatory PVs for all servers, that are created by default.
# EPICS PVs for iocStats, see https://epics.anl.gov/base/R3-14/7-docs/iocstats.html
['HOSTNAME',    'Server host name',  gethostname()],
['VERSION',     'Program version',  'epicsdev '+__version__],
['HEARTBEAT',   'Server heartbeat, Increments once per second', 0., {U:'S'}],
['UPTIME',      'Server uptime in seconds', '', {U:'S'}],
['STARTTOD',    'Server start time', time.strftime("%m/%d/%Y %H:%M:%S")],
['CPU_LOAD',    'CPU load in %', 0., {U:'%'}],
['CA_CONN_COUNT', 'Number of TCP connections', 0],
# Other popular stats: CA_CLIENTS, CA_CONN_COUNT, CPU_LOAD, FD_USED, THREAD_COUNT

# Epicsdev-specific PVs
['status',  'Server status. Features: RWE', '', {F:'W'}],
['server',  'Server control. Features: RWE',
    'Start Stop Clear Exit Started Stopped Exited'.split(),
    {F:'WD', 'setter':set_server}],
['verbose', 'Debugging verbosity',
    C_.verbose, {F:'W', T:'u8', 'setter':set_verbose, LL:0,LH:3}],
['sleep', 'Pause in the main loop, it could be useful for throttling the data output',
    1.0, {F:'W', T:'f32', U:'S', LL:0.001, LH:10.1}],
['cycle',   'Cycle number, published every {PeriodicUpdateInterval} S.',
    0, {T:'u32'}],
['cycleTime','Average cycle time including sleep, published every {PeriodicUpdateInterval} S',
    0., {U:'S'}],
    ]
    # append application's PVs, defined in the pvDefs and create map of
    #  providers
    if pvDefs is not None:
        C_.PVDefs += pvDefs
    create_PVs(C_.PVDefs, pvcache)
    return C_.PVs

def init_epicsdev(prefix:str, pvDefs:list, verbose=0, serverStateChanged=None,
        listDir=None, autosaveDir=None, recall = True, putlogPV=None):
    """Initialize epicsdev with given prefix and PV definitions.
    prefix is a string that will be prepended to all PV names. It should end with ':'.
    pvDefs is a list of PV definitions, each definition is a list of 3 or 4 items:
        [pvName, description, initialValue, extraParameters]
        pvName is the name of the PV (without prefix)
        description is a string with the description of the PV
        initialValue is the initial value of the PV
        extraParameters is a dictionary with optional keys:
            'features': string with characters W (writable), D (discrete). For example. By default, PV is read-only scalar.
            'type': string with data type, for example 'f32', 'i32', 's8', etc. By default, the type is determined from the initial value (float -> 'f32', int -> 'i32').
            'units': string with physical units, for example 'V', 'S', 'Mpts/s', etc.
            'limitLow': number with low limit for the value. If defined, then the put handler will check that the value is not below the low limit.
            'limitHigh': number with high limit for the value. If defined, then the put handler will check that the value is not above the high limit.
            'setter': function to be called when the PV value is changed. The function should have the signature:
                def setter(value, spv):
                where value is the new value, and spv is the SharedPV object.
    verbose is an integer that controls the verbosity level for debugging.
    serverStateChanged is a function that will be called when the server state changes. It should have the signature:
        def serverStateChanged(newState:str):
        where newState is the new state of the server ('Start', 'Stop', 'Exit', 'Clear').
    listDir is a string that specifies the directory where the list of PVs will be saved. If '', then no list will be saved.
    autosaveDir is a string that specifies the directory where the autosave file will be saved. If None, then no autosave will be performed.
    recall is a boolean that specifies whether to load initial values from the autosave file. If False, then the initial values will be taken from the PV definitions.
    """

    if not isinstance(verbose, int) or verbose < 0:
        printe('init_epicsdev arguments should be (prefix:str, pvDefs:list, verbose:int, listDir:str)')
        sys.exit(1)
    printi(f'Initializing epicsdev with prefix {prefix}')
    C_.prefix = prefix
    C_.verbose = verbose

    # Check if the server is already running by trying to get the value of HOSTNAME PV.
    # If it is accessible, then the server is already running, and we should exit to avoid conflicts.
    # If it is not accessible, then we can proceed with creating PVs and starting the server.
    if serverStateChanged is not None:# set custom serverStateChanged function
        C_.serverStateChanged = serverStateChanged
    try: # check if server is already running
        host = repr(IFace.get(prefix+'HOSTNAME', timeout=0.5)).replace("'",'')
        print(f'ERROR: Server for {prefix} already running at {host}. Exiting.')
        sys.exit(1)
    except TimeoutError:
        pass

    # No existing server found. Creating PVs.
    pvcache = {}
    if autosaveDir == '':# --autosave not given: use env-based default if available
        operations_dir = os.getenv('OPERATIONS')
        if operations_dir:
            autosaveDir = os.path.join(operations_dir, 'app_store', 'pvCache')
        else:
            autosaveDir = AutosaveDefaultDirectory
    if recall and autosaveDir is not None:
        try:
            autosaveFile = os.path.join(autosaveDir, f'{prefix[:-1]}.cache')
            with open(autosaveFile, "r") as json_file:
                pvcache = json.load(json_file)
        except Exception:
            print(f'WARNING: pvCache file {autosaveFile} not found. Using default values')
    if len(pvcache) == 0:
        printi('Loading default values')
    else:
        printi(f'Loading initial values from {autosaveFile}')
        printv(f'pvCache: {pvcache}')
    pvs = create_pvDefs(pvDefs, pvcache)

    # Set up autosave if requested. That will save PV values to a file, and restore them on the next startup.
    if autosaveDir is not None:
        try:
            os.makedirs(autosaveDir, exist_ok=True)
        except PermissionError:
            printe(f'Permission denied to create {autosaveDir}. You can define the root directory in OPERATIONS environment variable or disable autosaving.')
            sys.exit(1)
        autosaveFile = os.path.join(autosaveDir, f'{prefix[:-1]}.cache')
        C_.cachefd = open(autosaveFile, 'w')
        printi(f'Autosave enabled. Saving to {autosaveFile}')
    else:
        printi('Autosave disabled')

    # Set up putlogPV if requested. That will log put operations to a PV, which can be useful for auditing and debugging.
    C_.putlogPV = putlogPV
    if C_.putlogPV is not None:
        try:
            _ = IFace.get(putlogPV, timeout=0.5)
            printi(f'PutLog enabled. Logging put operations to {putlogPV}')
        except TimeoutError:
            printw(f'WARNING: PutLog feature will not work: PV {putlogPV} not accessible.')
            C_.putlogPV = None
    else:
        printw('PutLog feature is disabled.')

    # Save list of PVs to a file, if requested.
    if listDir != '':
        listDir = '/tmp/pvlist/' if listDir is None else listDir
        if not os.path.exists(listDir):
            os.makedirs(listDir)
        filepath = f'{listDir}{prefix[:-1]}.txt'
        printi(f'Writing list of PVs to {filepath}')
        with open(filepath, 'w', encoding="utf-8") as f:
            for _pvname in pvs:
                f.write(_pvname + '\n')
    printi(f'Hosting {len(pvs)} PVs')

    # Start the heartbeat thread, that will update heartbeat and uptime PVs.
    C_.startTime = time.time()
    threading.Thread(target=_heartbeat_thread, daemon=True).start()
    return pvs

def _heartbeat_thread():
    """Thread to update heartbeat and uptime PVs."""
    while True:
        time.sleep(1)
        publish('HEARTBEAT', pvv('HEARTBEAT')+1)
        publish('UPTIME', round(time.time() - C_.startTime, 1))

def sleep():
    """Sleep function to be called in the main loop. It updates cycleTime PV
    and sleeps for the time specified in sleep PV.
    Returns False if a periodic update occurred.
    """
    time.sleep(pvv('sleep'))
    sleeping = True
    if serverState().startswith('Stop'):
        return sleeping
    tnow = timer()
    C_.cycleTimeSum += tnow - C_.lastCycleTime
    C_.lastCycleTime = tnow
    C_.cyclesAfterUpdate += 1
    C_.cycle += 1
    printv(f'cycle {C_.cycle}')
    if tnow - C_.lastUpdateTime > PeriodicUpdateInterval:
        avgCycleTime = C_.cycleTimeSum / C_.cyclesAfterUpdate
        printv(f'Average cycle time: {avgCycleTime:.6f} S.')
        publish('cycle', C_.cycle)
        publish('cycleTime', avgCycleTime)
        publish('CPU_LOAD', round(psutil.cpu_percent(),1))
        publish('CA_CONN_COUNT', len(psutil.net_connections(kind='tcp')))
        C_.lastUpdateTime = tnow
        C_.cycleTimeSum = 0.
        C_.cyclesAfterUpdate = 0
        sleeping = False

    if C_.cachefd is not None and tnow - C_.lastAutosaveTime > AutosaveInterval:
        C_.lastAutosaveTime = tnow
        if C_.lastPutTime != 0.:
            C_.lastPutTime = 0.
            write_cache()
        else:
            printv('No changes to save')
    return sleeping

#``````````````````Demo````````````````````````````````````````````````````````
if __name__ == "__main__":
    import argparse

    def myPVDefs():
        """Example of PV definitions"""
        F,T,U,LL,LH,SET = 'features','type','units','limitLow','limitHigh','setter'
        alarm = {'valueAlarm':{'lowAlarmLimit':-9., 'highAlarmLimit':9.}}
        return [    # device-specific PVs
['noiseLevel',  'Noise amplitude',  1., {F:'W', U:'V'}],
['tAxis',       'Full scale of horizontal axis', [0.], {U:'S'}],
['recordLength','Max number of points',
    100, {F:'W', T:'u32', LL:4,LH:1000000, SET:set_recordLength}],
['throughput', 'Performance metrics, points per second', 0., {U:'Mpts/s'}],
['c01Offset',   'Offset',                   0., {F:'W', U:'du'}],
['c01VoltsPerDiv',  'Vertical scale',       0.1, {F:'W', U:'V/du'}],
['c01Waveform', 'Waveform array',           [0.], {U:'du'}],
['c01Mean',     'Mean of the waveform',     0., {U:'du'}],
['c01Peak2Peak','Peak-to-peak amplitude',   0., {U:'du', **alarm}],
['waveform',    'int16 waveform',           [0], {T:'u16', U:'du'}],
['image',       'Image array',              np.zeros((1,1), dtype='int16')],
['alarm',       'PV with alarm',            0, {U:'du', **alarm}],
        ]

    pargs = None
    rng = np.random.default_rng()
    _sum = {'points': 0, 'time': 0.}

    def set_recordLength(value, *_):
        """Record length have changed. The tAxis should be updated
        accordingly."""
        printi(f'Setting tAxis to {value}')
        publish('tAxis', np.arange(value)*1.E-6)

    def init(recordLength):
        """Example of device initialization function"""
        set_recordLength(recordLength)

    def poll():
        """Example of polling function. Called every cycle when server is running.
            It returns time, spent in publishing data"""
        wf = rng.random(pvv('recordLength'))*pvv('noiseLevel')# it takes 5ms for 1M points
        wf /= pvv('c01VoltsPerDiv')
        wf += pvv('c01Offset')
        ts = timer()        
        publish('c01Waveform', wf)
        publish('waveform', wf*10)
        _sum['time'] += timer() - ts
        _sum['points'] += len(wf)
        publish('c01Peak2Peak', np.ptp(wf))
        publish('c01Mean', np.mean(wf))

        # For demo purposes, we also publish the waveform as an image. That is not a typical use case, but it shows how to publish 2D arrays.
        dim = int(np.sqrt(len(wf)))
        array2d = (wf*10.)[:dim*dim].reshape([dim, dim])
        publish('image', array2d.astype('int16'))

    def periodic_update():
        """Perform periodic update"""
        #printi(f'periodic update for {C_.cyclesSinceUpdate} cycles: {ElapsedTime}')
        if state.startswith('Stop'):
            publish('throughput', 0.)
        else:
            pointsPerSecond = _sum['points']/_sum['time']/1.E6
            publish('throughput', round(pointsPerSecond,6))
            printv(f'periodic update. Performance: {pointsPerSecond:.3g} Mpts/s')
            _sum['points'] = 0
            _sum['time'] = 0.

    # Parse command line arguments  
    parser = argparse.ArgumentParser(description = __doc__,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog=f'{__version__}')
    parser.add_argument('-a', '--autosave', nargs='?', default='', help=
'Autosave control. If not given, then autosave is enabled with default '
'directory $OPERATIONS/app_store/pvCache when OPERATIONS is defined, '
'otherwise /operations/app_store/pvCache. ' \
'If given without argument, then autosave is disabled' \
'If a file name is given, then it is used for autosave.')
    parser.add_argument('-c', '--recall', action='store_false', help=
'If given: Do not load initial values from pvCache file. That is useful when you want to start with default values, but do not want to disable autosave. By default, the initial values are loaded from the cache file if it exists.')
    parser.add_argument('-d', '--device', default='epicsDev', help=
'Device name, the PV name will be <device><index>:')
    parser.add_argument('-i', '--index', default='0', help=
'Device index, the PV name will be <device><index>:') 
    parser.add_argument('-l', '--list', nargs='?', help=(
'Directory to save list of all generated PVs, if no directory is given, '
'then </tmp/pvlist/><prefix> is assumed.'))
    # The rest of options are not essential, they can be controlled at runtime using PVs.
    parser.add_argument('-n', '--npoints', type=int, default=100, help=
'Number of points in the waveform')
    parser.add_argument('-p', '--putlogPV', nargs='?', default='', help=
'PV name for logging put operations. If given without argument, then putlog is disabled. If not given, then putlog is set to "putlog:dump".')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=
'Show more log messages (-vv: show even more)') 
    pargs = parser.parse_args()
    if pargs.putlogPV == '':
        pargs.putlogPV = 'putlog:dump'
    print(pargs)

    # Initialize epicsdev and PVs
    pargs.prefix = f'{pargs.device}{pargs.index}:'
    PVs = init_epicsdev(pargs.prefix, myPVDefs(), pargs.verbose, None,
                    pargs.list, pargs.autosave, pargs.recall, pargs.putlogPV)
    # Initialize the device using pargs if needed.
    init(pargs.npoints)

    # Start the Server. Use your set_server, if needed.
    set_server('Start')

    # Main loop
    # In this example, we just update the waveform,image and its stats in a loop,
    # but in a real application, the loop can also read data from the device,
    # and update PVs accordingly. The loop can be paused by setting server PV to 'Stop',
    # and exited by setting server PV to 'Exit'. 
    # The performance metrics are updated every {PeriodicUpdateInterval} seconds.
    server = Server(providers=[PVs])
    printi(f'Server started. Sleeping per cycle: {repr(pvv("sleep"))} S.')
    while True:
        state = serverState()
        if state.startswith('Exit'):
            break
        if not state.startswith('Stop'):
            poll()
        if not sleep():# Sleep and update performance metrics periodically
            periodic_update()
    printi('Server is exited')
