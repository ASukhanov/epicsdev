"""Skeleton and helper functions for creating EPICS PVAccess server"""
# pylint: disable=invalid-name
__version__= 'v1.0.2 26-01-18'# --list define directory to save list of PVs.
#TODO: NTEnums do not have structure display
#TODO: Add performance counters to demo.
#Issue: There is no way in PVAccess to specify if string PV is writable.
# As a workaround we append description with suffix ' Features: W' to indicate that.

import sys
import time
from time import perf_counter as timer
import os
from p4p.nt import NTScalar, NTEnum
from p4p.nt.enum import ntenum
from p4p.server import Server
from p4p.server.thread import SharedPV
from p4p.client.thread import Context

#``````````````````Module Storage`````````````````````````````````````````````
class C_():
    """Storage for module members"""
    prefix = ''
    verbose = 0
    cycle = 0
    serverState = ''
    PVs = {}
    PVDefs = []
#```````````````````Helper methods````````````````````````````````````````````
def serverState():
    """Return current server state. That is the value of the server PV, but cached in C_ to avoid unnecessary get() calls."""
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
    """Publish value to PV. If ifChanged is True, then publish only if the value is different from the current value. If t is not None, then use it as timestamp, otherwise use current time."""
    try:
        pv = pvobj(pvName)
    except KeyError:
        printw(f'PV {pvName} not found. Cannot publish value.')
        return
    if t is None:
        t = time.time()
    if not ifChanged or pv.current() != value:
        pv.post(value, timestamp=t)

def SPV(initial, meta='', vtype=None):
    """Construct SharedPV.
    meta is a string with characters W,A,E indicating if the PV is writable, has alarm or it is NTEnum.
    vtype should be one of the p4p.nt type definitions (see https://epics-base.github.io/p4p/values.html).
    if vtype is None then the nominal type will be determined automatically.
    """
    typeCode = {
    's8':'b', 'u8':'B', 's16':'h', 'u16':'H', 'i32':'i', 'u32':'I', 'i64':'l',
    'u64':'L', 'f32':'f', 'f64':'d', str:'s',
    }
    iterable  = type(initial) not in (int,float,str)
    if vtype is None:
        firstItem = initial[0] if iterable else initial
        itype = type(firstItem)
        vtype = {int: 'i32', float: 'f32'}.get(itype,itype)
    tcode = typeCode[vtype]
    if 'E' in meta:
        initial = {'choices': initial, 'index': 0}
        nt = NTEnum(display=True, control='W' in meta)
    else:
        prefix = 'a' if iterable else ''
        nt = NTScalar(prefix+tcode, display=True, control='W' in meta, valueAlarm='A' in meta)
    pv = SharedPV(nt=nt, initial=initial)
    pv.writable = 'W' in meta
    return pv

#``````````````````create_PVs()```````````````````````````````````````````````
def _create_PVs(pvDefs):
    """Create PVs, using definitions from pvDEfs list. Each definition is a list of the form:
[pvname, description, SPV object, extra], where extra is a dictionary of extra parameters, like setter, units, limits etc. Setter is a function, that will be called when"""
    ts = time.time()
    for defs in pvDefs:
        try:
            pname,desc,spv,extra = defs
        except ValueError:
            printe(f'Invalid PV definition of {defs[0]}')
            sys.exit(1)
        ivalue = spv.current()
        printv(f'created pv {pname}, initial: {type(ivalue),ivalue}, extra: {extra}')
        C_.PVs[C_.prefix+pname] = spv
        v = spv._wrap(ivalue, timestamp=ts)
        if spv.writable:
            try:
                # To indicate that the PV is writable, set control limits to (0,0). Not very elegant, but it works for numerics and enums, not for strings.
                v['control.limitLow'] = 0
                v['control.limitHigh'] = 0
            except KeyError as e:
                #print(f'control not set for {pname}: {e}')
                pass
        if 'ntenum' in str(type(ivalue)):
            spv.post(ivalue, timestamp=ts)
        else:
            v['display.description'] = desc
            for field in extra.keys():              
                if field in ['limitLow','limitHigh','format','units']:
                    v[f'display.{field}'] = extra[field]
                    if field.startswith('limit'):
                        v[f'control.{field}'] = extra[field]
                if field == 'valueAlarm':
                    for key,value in extra[field].items():
                        v[f'valueAlarm.{key}'] = value
            spv.post(v)

        # add new attributes. To my surprise that works!
        spv.name = pname
        spv.setter = extra.get('setter')

        if spv.writable:
            @spv.put
            def handle(spv, op):
                ct = time.time()
                vv = op.value()
                vr = vv.raw.value
                current = spv._wrap(spv.current())
                # check limits, if they are defined. That will be a good example of using control structure and valueAlarm.
                try:
                    limitLow = current['control.limitLow']
                    limitHigh = current['control.limitHigh']
                    if limitLow != limitHigh and not (limitLow <= vr <= limitHigh):
                        printw(f'Value {vr} is out of limits [{limitLow}, {limitHigh}]. Ignoring.')
                        op.done(error=f'Value out of limits [{limitLow}, {limitHigh}]')
                        return
                except KeyError:
                    pass
                if isinstance(vv, ntenum):
                    vr = vv
                if spv.setter:
                    spv.setter(vr)
                    # value will be updated by the setter, so get it again
                    vr = pvv(spv.name)
                printv(f'putting {spv.name} = {vr}')
                spv.post(vr, timestamp=ct) # update subscribers
                op.done()
        #print(f'PV {pv.name} created: {spv}')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Setters
def set_verbosity(level):
    """Set verbosity level for debugging"""
    C_.verbose = level
    publish('verbosity',level)

def set_server(state=None):
    """Example of the setter for the server PV."""
    #printv(f'>set_server({state}), {type(state)}')
    if state is None:
        state = pvv('server')
        printi(f'Setting server state to {state}')
    state = str(state)
    if state == 'Start':
        printi('Starting the server')
        # configure_instrument()
        # adopt_local_setting()
        publish('server','Started')
        publish('status','Started')
    elif state == 'Stop':
        printi('server stopped')
        publish('server','Stopped')
        publish('status','Stopped')
    elif state == 'Exit':
        printi('server is exiting')
        publish('server','Exited')
        publish('status','Exited')
    elif state == 'Clear':
        publish('acqCount', 0)
        publish('status','Cleared')
        # set server to previous state
        set_server(C_.serverState)
    C_.serverState = state

def create_PVs(pvDefs=None):
    """Creates manadatory PVs and adds PVs specified in pvDefs list"""
    U,LL,LH = 'units','limitLow','limitHigh'
    C_.PVDefs = [
['version', 'Program version',  SPV(__version__), {}],
['status',  'Server status. Features: RWE',    SPV('?','W'), {}],
['server',  'Server control',   
    SPV('Start Stop Clear Exit Started Stopped Exited'.split(), 'WE'),
        {'setter':set_server}],
['verbosity', 'Debugging verbosity', SPV(0,'W','u8'),
        {'setter':set_verbosity}],
['polling', 'Polling interval', SPV(1.0,'W'), {U:'S', LL:0.001, LH:10.1}],
['cycle',   'Cycle number',         SPV(0,'','u32'), {}],
    ]
    # append application's PVs, defined in the pvDefs and create map of providers
    if pvDefs is not None:
        C_.PVDefs += pvDefs
    _create_PVs(C_.PVDefs)
    return C_.PVs

def get_externalPV(pvName:str, timeout=0.5):
    """Get value of PV from another server. That can be used to check if the
    server is already running, or to get values from other servers."""
    ctxt = Context('pva')
    return ctxt.get(pvName, timeout=timeout)

def init_epicsdev(prefix:str, pvDefs:list, listDir:str, verbose:str=0):
    """Check if no other server is running with the same prefix.
    Create PVs and return them as a dictionary.
    The listDir is a directory to save list of all generated PVs,
    if no directory is given, then </tmp/pvlist/><prefix> is assumed.
    """
    C_.prefix = prefix
    C_.verbose = verbose
    try:
        get_externalPV(prefix+'version')
        print(f'ERROR: Server for {prefix} already running. Exiting.')
        sys.exit(1)
    except TimeoutError:
        pass
    pvs = create_PVs(pvDefs)
    # Save list of PVs to a file, if requested
    if listDir != '':
        listDir = '/tmp/pvlist/' if listDir is None else listDir
        if not os.path.exists(listDir):
            os.makedirs(listDir)
        filepath = f'{listDir}{prefix[:-1]}.txt'
        print(f'Writing list of PVs to {filepath}')
        with open(filepath, 'w', encoding="utf-8") as f:
            for _pvname in pvs:
                f.write(_pvname + '\n')
    return pvs

#``````````````````Demo````````````````````````````````````````````````````````
if __name__ == "__main__":
    print(f'epicsdev multiadc demo server {__version__}')
    import numpy as np
    import argparse

    def myPVDefs():
        """Example of PV definitions"""
        SET,U,LL,LH = 'setter','units','limitLow','limitHigh'
        alarm = {'valueAlarm':{'lowAlarmLimit':-9., 'highAlarmLimit':9.}}
        return [    # device-specific PVs
['noiseLevel',  'Noise amplitude',  SPV(1.E-6,'W'), {SET:set_noise, U:'V'}],
['tAxis',       'Full scale of horizontal axis', SPV([0.]), {U:'S'}],
['recordLength','Max number of points',     SPV(100,'W','u32'),
    {LL:4,LH:1000000, SET:set_recordLength}],
['ch1Offset',   'Offset',  SPV(0.,'W'), {U:'du'}],
['ch1VoltsPerDiv',  'Vertical scale',       SPV(1E-3,'W'), {U:'V/du'}],
['ch1Waveform', 'Waveform array',           SPV([0.]), {U:'du'}],
['ch1Mean',     'Mean of the waveform',     SPV(0.,'A'), {U:'du'}],
['ch1Peak2Peak','Peak-to-peak amplitude',   SPV(0.,'A'), {U:'du',**alarm}],
['alarm',       'PV with alarm',            SPV(0,'WA'), {U:'du',**alarm}],
        ]
    nPatterns = 100 # number of waveform patterns.
    pargs = None
    rng = np.random.default_rng(nPatterns)
    nPoints = 100

    def set_recordLength(value):
        """Record length have changed. The tAxis should be updated accordingly."""
        printi(f'Setting tAxis to {value}')
        publish('tAxis', np.arange(value)*1.E-6)
        publish('recordLength', value)
        set_noise(pvv('noiseLevel')) # Re-initialize noise array, because its size depends on recordLength

    def set_noise(level):
        """Noise level have changed. Update noise array."""
        v = float(level)
        recordLength = pvv('recordLength')
        ts = timer()
        pargs.noise = np.random.normal(scale=0.5*level, size=recordLength+nPatterns)# 45ms/1e6 points
        printi(f'Noise array[{len(pargs.noise)}] updated with level {v:.4g} V. in {timer()-ts:.4g} S.')
        publish('noiseLevel', level)

    def init(recordLength):
        """Testing function. Do not use in production code."""
        set_recordLength(recordLength)
        #set_noise(pvv('noiseLevel')) # already called from set_recordLength

    def poll():
        """Example of polling function"""
        #pattern = C_.cycle % nPatterns# produces sliding
        pattern = rng.integers(0, nPatterns)
        cycle = pvv('cycle')
        printv(f'cycle {repr(cycle)}')
        publish('cycle', cycle + 1)
        wf = pargs.noise[pattern:pattern+pvv('recordLength')].copy()
        wf /= pvv('ch1VoltsPerDiv')
        wf += pvv('ch1Offset')
        publish('ch1Waveform', wf)
        publish('ch1Peak2Peak', np.ptp(wf))
        publish('ch1Mean', np.mean(wf))

    # Argument parsing
    parser = argparse.ArgumentParser(description = __doc__,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog=f'{__version__}')
    parser.add_argument('-l', '--list', default='', nargs='?', help=
'Directory to save list of all generated PVs, if no directory is given, then </tmp/pvlist/><prefix> is assumed.')
    parser.add_argument('-p', '--prefix', default='epicsDev0:', help=
'Prefix to be prepended to all PVs')
    # The rest of options are not essential, they can be controlled at runtime using PVs.
    parser.add_argument('-n', '--npoints', type=int, default=nPoints, help=
'Number of points in the waveform')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=
'Show more log messages (-vv: show even more)') 
    pargs = parser.parse_args()
    print(pargs)

    # Initialize epicsdev and PVs
    PVs = init_epicsdev(pargs.prefix, myPVDefs(), pargs.list, pargs.verbose)

    # Initialize the device, using pargs if needed. That can be used to set the number of points in the waveform, for example.
    init(pargs.npoints)

    # Start the Server. Use your set_server, if needed.
    set_server('Start')

    # Main loop
    server = Server(providers=[PVs])
    printi(f'Server started with polling interval {repr(pvv("polling"))} S.')
    while True:
        state = serverState()
        if state.startswith('Exit'):
            break
        if not state.startswith('Stop'):
            poll()
        time.sleep(pvv("polling"))
    printi('Server is exited')
