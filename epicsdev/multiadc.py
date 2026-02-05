"""Simulated multi-channel ADC device server using epicsdev module."""
# pylint: disable=invalid-name
__version__= 'v2.1.1 26-02-04'# added timing, throughput and c0$VoltOffset PVs

import sys
from time import perf_counter as timer
import argparse
import numpy as np

from .epicsdev import  Server, Context, init_epicsdev, serverState, publish
from .epicsdev import  pvv, printi, printv, SPV, set_server, sleep


def myPVDefs():
    """Example of PV definitions"""
    SET,U,LL,LH = 'setter','units','limitLow','limitHigh'
    alarm = {'valueAlarm':{'lowAlarmLimit':-9., 'highAlarmLimit':9.}}
    pvDefs = [    # device-specific PVs
['channels',    'Number of device channels',    SPV(pargs.channels), {}],
['externalControl', 'Name of external PV, which controls the server',
    SPV('Start Stop Clear Exit Started Stopped Exited'.split(), 'WD'), {}], 
['noiseLevel',  'Noise amplitude',  SPV(0.05,'W'), {U:'V'}],
['tAxis',       'Full scale of horizontal axis', SPV([0.]), {U:'S'}],
['recordLength','Max number of points',     SPV(100,'W','u32'),
    {LL:4,LH:1000000, SET:set_recordLength}],
['alarm',       'PV with alarm',            SPV(0,'WA'), {U:'du',**alarm}],
#``````````````````Auxiliary PVs
['timing',  'Elapsed time for waveform generation, publishing, total]', SPV([0.]), {U:'S'}],
['throughput', 'Total number of points processed per second', SPV(0.), {U:'Mpts/s'}],
    ]

    # Templates for channel-related PVs. Important: SPV cannot be used in this list!
    ChannelTemplates = [
['c0$VoltsPerDiv',  'Vertical scale',       (0.1,'W'), {U:'V/du'}],
['c0$VoltOffset',  'Vertical offset',       (0.,'W'), {U:'V'}],
['c0$Waveform', 'Waveform array',           ([0.],), {U:'du'}],
['c0$Mean',     'Mean of the waveform',     (0.,'A'), {U:'du'}],
['c0$Peak2Peak','Peak-to-peak amplitude',   (0.,'A'), {U:'du',**alarm}],
    ]
    # extend PvDefs with channel-related PVs
    for ch in range(pargs.channels):
        for pvdef in ChannelTemplates:
            newpvdef = pvdef.copy()
            newpvdef[0] = pvdef[0].replace('0$',f'{ch+1:02}')
            newpvdef[2] = SPV(*pvdef[2])
            pvDefs.append(newpvdef)
    return pvDefs

#``````````````````Module attributes
rng = np.random.default_rng()
ElapsedTime = {'waveform': 0., 'publish': 0., 'poll': 0.}
class C_():
    cyclesSinceUpdate = 0

#``````````````````Setter functions for PVs```````````````````````````````````
def set_recordLength(value, *_):
    """Record length have changed. The tAxis should be updated accordingly."""
    printi(f'Setting tAxis to {value}')
    publish('tAxis', np.arange(value)*1.E-6)
    publish('recordLength', value)

def set_externalControl(value, *_):
    """External control PV have changed. Control the server accordingly."""
    pvname = str(value)
    if pvname in (None,'0'):
        print('External control is not activated.')
        return
    printi(f'External control PV: {pvname}')
    ctxt = Context('pva')
    try:
        r = ctxt.get(pvname, timeout=0.5)
    except TimeoutError:
        printi(f'Cannot connect to external control PV {pvname}.')
        sys.exit(1)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
def serverStateChanged(newState:str):
    """Start device function called when server is started"""
    if newState == 'Start':
        printi('start_device called')
    elif newState == 'Stop':
        printi('stop_device called')
    elif newState == 'Clear':
        printi('clear_device called')
        publish('cycle', 0)

def init(recordLength):
    """Device initialization function"""
    set_recordLength(recordLength)
    # Set offset of each channel = channel index
    for ch in range(pargs.channels):
        publish(f'c{ch+1:02}VoltOffset', ch)
    #set_externalControl(pargs.prefix + pargs.external)

def poll():
    """Device polling function, called every cycle when server is running"""
    C_.cyclesSinceUpdate += 1
    ts0 = timer()
    for ch in range(pargs.channels):
        ts1 = timer()
        chstr = f'c{ch+1:02}'
        rwf = rng.random(pvv('recordLength'))*pvv('noiseLevel')
        wf = rwf/pvv(f'{chstr}VoltsPerDiv') + pvv(f'{chstr}VoltOffset')# the time is comparable with rng.random
        ts2 = timer()
        ElapsedTime['waveform'] += ts2 - ts1
        #print(f'ElapsedTime: {C_.cyclesSinceUpdate, ElapsedTime["waveform"]}')
        publish(f'{chstr}Waveform', wf)
        publish(f'{chstr}Peak2Peak', np.ptp(wf))
        publish(f'{chstr}Mean', np.mean(wf))
        ElapsedTime['publish'] += timer() - ts2
    ElapsedTime['poll'] += timer() - ts0

def periodic_update():
    """Perform periodic update"""
    #printi(f'periodic update for {C_.cyclesSinceUpdate} cycles: {ElapsedTime}')
    times = [(round(i/C_.cyclesSinceUpdate,6)) for i in ElapsedTime.values()]
    publish('timing', times)
    C_.cyclesSinceUpdate = 0
    for key in ElapsedTime:
        ElapsedTime[key] = 0.
    pointsPerSecond = len(pvv('tAxis'))/(pvv('cycleTime')-pvv('sleep'))/1.E6
    pointsPerSecond *= pvv('channels')
    publish('throughput', round(pointsPerSecond,6))
    printv(f'periodic update. Performance: {pointsPerSecond:.3g} Mpts/s')


# Argument parsing
parser = argparse.ArgumentParser(description = __doc__,
formatter_class=argparse.ArgumentDefaultsHelpFormatter,
epilog=f'{__version__}')
parser.add_argument('-c', '--channels', type=int, default=6, help=
'Number of channels per device')
parser.add_argument('-e', '--external', help=
'Name of external PV, which controls the server, if 0 then it will be <device>0:')
parser.add_argument('-l', '--list', default=None, nargs='?', help=
'Directory to save list of all generated PVs, if None, then </tmp/pvlist/><prefix> is assumed.')
parser.add_argument('-d', '--device', default='multiadc', help=
'Device name, the PV name will be <device><index>:')
parser.add_argument('-i', '--index', default='0', help=
'Device index, the PV name will be <device><index>:') 
# The rest of arguments are not essential, they can be changed at runtime using PVs.
parser.add_argument('-n', '--npoints', type=int, default=100, help=
'Number of points in the waveform')
parser.add_argument('-v', '--verbose', action='count', default=0, help=
'Show more log messages (-vv: show even more)') 
pargs = parser.parse_args()
print(f'pargs: {pargs}')

# Initialize epicsdev and PVs
pargs.prefix = f'{pargs.device}{pargs.index}:'
PVs = init_epicsdev(pargs.prefix, myPVDefs(), pargs.verbose,
                    serverStateChanged, pargs.list)

# Initialize the device, using pargs if needed. 
# That can be used to set the number of points in the waveform, for example.
init(pargs.npoints)

# Start the Server. Use your set_server, if needed.
set_server('Start')

#``````````````````Main loop``````````````````````````````````````````````````
server = Server(providers=[PVs])
printi(f'Server started. Sleeping per cycle: {repr(pvv("sleep"))} S.')
while True:
    state = serverState()
    if state.startswith('Exit'):
        break
    if not state.startswith('Stop'):
        poll()
    if not sleep():
        periodic_update()
printi('Server has exited')
