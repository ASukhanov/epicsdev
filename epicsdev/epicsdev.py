"""Skeleton and helper functions for creating EPICS PVAccess server"""
# pylint: disable=invalid-name
__version__= 'v0.0.0 26-01-14'# Created
#TODO: Do not start if another device is already running
#TODO: NTEnums do not have structure display
#TODO: Find a way to indicate that a PV is writable.
# Options:
# 1) add structure control with (0,0) limits as indication of Writable.
# 2) use an extra field of the NTScalar.

import argparse
import time
from p4p.nt import NTScalar, NTEnum
from p4p.nt.enum import ntenum
from p4p.server import Server
from p4p.server.thread import SharedPV

#``````````````````Module Storage`````````````````````````````````````````````
class C_():
    """Storage for module members"""
    AppName = 'epicsDevLecroyScope'
    cycle = 0
    lastRareUpdate = 0.
    server = None
    serverState = ''
    PVs = {}
    PVDefs = []
#```````````````````Helper methods````````````````````````````````````````````
def printTime(): return time.strftime("%m%d:%H%M%S")
def printi(msg): print(f'inf_@{printTime()}: {msg}')
def printw(msg):
    txt = f'WAR_@{printTime()}: {msg}'
    print(txt)
    #publish('status',txt)
def printe(msg):
    txt = f'ERR_{printTime()}: {msg}'
    print(txt)
    #publish('status',txt)
def _printv(msg, level):
    if pargs.verbose >= level: print(f'DBG{level}: {msg}')
def printv(msg): _printv(msg, 1)
def printvv(msg): _printv(msg, 2)
def printv3(msg): _printv(msg, 3)

def pvobj(pvname):
    """Return PV with given name"""
    return C_.PVs[pargs.prefix+pvname]

def pvv(pvname:str):
    """Return PV value"""
    return pvobj(pvname).current()

def publish(pvname:str, value, ifChanged=False, t=None):
    """Post PV with new value"""
    try:
        pv = pvobj(pvname)
    except KeyError:
        return
    if t is None:
        t = time.time()
    if not ifChanged or pv.current() != value:
        pv.post(value, timestamp=t)

def SPV(initial, vtype=None):
    """Construct SharedPV, vtype should be one of typeCode keys,
    if vtype is None then the nominal type will be determined automatically
    """
    typeCode = {
    'F64':'d',  'F32':'f',  'I64':'l',  'I8':'b',   'U8':'B',   'I16':'h',
    'U16':'H',  'I32':'i',  'U32':'I', str:'s', 'enum':'enum',
    }
    iterable  = type(initial) not in (int,float,str)
    if vtype is None:
        firstItem = initial[0] if iterable else initial
        itype = type(firstItem)
        vtype = {int: 'I32', float: 'F32'}.get(itype,itype)
    tcode = typeCode[vtype]
    if tcode == 'enum':
        initial = {'choices': initial, 'index': 0}
        nt = NTEnum(display=True)#TODO: that does not work
    else:
        prefix = 'a' if iterable else ''
        nt = NTScalar(prefix+tcode, display=True, control=True, valueAlarm=True)
    return SharedPV(nt=nt, initial=initial)

#``````````````````Definition of PVs``````````````````````````````````````````
def _define_PVs():
    """Example of PV definitions"""
    R,W,SET,U,ENUM,LL,LH = 'R','W','setter','units','enum','limitLow','limitHigh'
    alarm = {'valueAlarm':{'lowAlarmLimit':0, 'highAlarmLimit':100}}
    return [
# device-specific PVs
['VoltOffset',  'Offset',  SPV(0.), W, {U:'V'}],
['VoltPerDiv',  'Vertical scale',   SPV(0.), W, {U:'V/du'}],
['TimePerDiv',  'Horizontal scale', SPV('0.01 0.02 0.05 0.1 0.2 0.5 1 2 5'.split(),ENUM), W, {U:'S/du'}],
['trigDelay',   'Trigger delay',    SPV(0.), W, {U:'S'}],
['Waveform',    'Waveform array',   SPV([0.]), R, {}],
['tAxis',       'Full scale of horizontal axis', SPV([0.]), R,  {}],
['recordLength','Max number of points',     SPV(100,'U32'), W, {}],
['peak2peak',   'Peak-to-peak amplitude',   SPV(0.), R,     {}],
['alarm',       'PV with alarm',    SPV(0), 'WA', alarm],
    ]

#``````````````````create_PVs()```````````````````````````````````````````````
def _create_PVs():
    """Create PVs"""
    ts = time.time()
    for defs in C_.PVDefs:
        pname,desc,spv,features,extra = defs
        pv = spv
        ivalue = pv.current()
        printv(f'created pv {pname}, initial: {type(ivalue),ivalue}, extra: {extra}')
        C_.PVs[pargs.prefix+pname] = pv
        #if isinstance(ivalue,dict):# NTEnum
        if 'ntenum' in str(type(ivalue)):
            pv.post(ivalue, timestamp=ts)
        else:
            v = pv._wrap(ivalue, timestamp=ts)
            v['display.description'] = desc
            for field in extra.keys():
                if field in ['limitLow','limitHigh','format','units']:
                    v[f'display.{field}'] = extra[field]
                    if field.startswith('limit'):
                        v[f'control.{field}'] = extra[field]
                if field == 'valueAlarm':
                    for key,value in extra[field].items():
                        v[f'valueAlarm.{key}'] = value
            pv.post(v)

        # add new attributes. To my surprise that works!
        pv.name = pname
        pv.setter = extra.get('setter')

        writable = 'W' in features
        if writable:
            @pv.put
            def handle(pv, op):
                ct = time.time()
                vv = op.value()
                vr = vv.raw.value
                if isinstance(vv, ntenum):
                    vr = vv
                if pv.setter:
                    pv.setter(vr)
                    # value could change by the setter
                    vr = pvv(pv.name)
                printv(f'putting {pv.name} = {vr}')
                pv.post(vr, timestamp=ct) # update subscribers
                op.done()
        #print(f'PV {pv.name} created: {pv}')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Setters
def set_verbosity(level):
    """Set verbosity level for debugging"""
    pargs.verbose = level
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
        #configure_scope()
        #adopt_local_setting()
        publish('server','Started')
    elif state == 'Stop':
        printi('server stopped')
        publish('server','Stopped')
    elif state == 'Exit':
        printi('server is exiting')
        publish('server','Exited')
    elif state == 'Clear':
        publish('acqCount', 0)
        #publish('lostTrigs', 0)
        #C_.triggersLost = 0
        publish('status','Cleared')
        # set server to previous state
        set_server(C_.serverState)
    C_.serverState = state

def poll():
    """Example of polling function"""
    C_.cycle += 1
    printv(f'cycle {C_.cycle}')
    publish('cycle', C_.cycle)

def create_PVs(pvDefs:list):
    """Creates manadatory PVs and adds PVs, using definitions from pvDEfs list"""
    U,LL,LH = 'units','limitLow','limitHigh'
    C_.PVDefs = [
['version', 'Program version',  SPV(__version__),    'R', {}],
['status',  'Server status',    SPV('?'),   'W', {}],
['server',  'Server control',   
    SPV('Start Stop Clear Exit Started Stopped Exited'.split(), 'enum'), 
    'W', {'setter':set_server}],
['verbosity', 'Debugging verbosity', SPV(0,'U8'), 'W',
    {'setter':set_verbosity}],
['polling', 'Polling interval', SPV(1.0), 'W', {U:'S', LL:0.001, LH:10.1}],
['cycle',   'Cycle number',         SPV(0,'U32'), 'R',  {}],
    ]
    # append application PVs, defined in define_PVs()
    C_.PVDefs += pvDefs
    _create_PVs()
    return C_.PVs

#``````````````````Example of the Main() function````````````````````````````
if __name__ == "__main__":
    # Argument parsing
    parser = argparse.ArgumentParser(description = __doc__,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog=f'{__version__}')
    parser.add_argument('-c','--channels', type=int, default=4, help=
        'Number of channels in the scope')
    parser.add_argument('-p', '--prefix', default='epicsDev:', help=
        'Prefix to be prepended to all PVs')
    parser.add_argument('-l', '--listPVs', action='store_true', help=\
    'List all generated PVs')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=\
    'Show more log messages (-vv: show even more)')
    pargs = parser.parse_args()

    PVs = create_PVs(_define_PVs())# Provide your PV definitions instead of _define_PVs()

    # List the PVs
    if pargs.listPVs:
        print(f'List of PVs:')
        for pvname in PVs:
            print(pvname)

    # Start the Server. Use your set_server, if needed.
    set_server('Start')

    # Main loop
    server = Server(providers=[PVs])
    printi(f'Server started with polling interval {repr(pvv("polling"))} S.')
    while not C_.serverState.startswith('Exit'):
        time.sleep(pvv("polling"))
        if not C_.serverState.startswith('Stop'):
            poll()
    printi('Server is exited')
