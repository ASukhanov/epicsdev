"""Simulated multi-channel ADC device server using epicsdev module."""
# pylint: disable=invalid-name
__version__= 'v0.0.2 26-01-23'# refactored, adjusted for epicdev 2.0.1

import sys
import time
from time import perf_counter as timer
import numpy as np
import argparse

from .epicsdev import  Server, Context, init_epicsdev, serverState, publish
from .epicsdev import  pvv, printi, printv, SPV, set_server


def myPVDefs():
    """Example of PV definitions"""
    SET,U,LL,LH = 'setter','units','limitLow','limitHigh'
    alarm = {'valueAlarm':{'lowAlarmLimit':-9., 'highAlarmLimit':9.}}
    pvDefs = [    # device-specific PVs
['externalControl', 'Name of external PV, which controls the server',
    SPV('Start Stop Clear Exit Started Stopped Exited'.split(), 'WD'), {}], 
['noiseLevel',  'Noise amplitude',  SPV(1.E-4,'W'), {SET:set_noise, U:'V'}],
['tAxis',       'Full scale of horizontal axis', SPV([0.]), {U:'S'}],
['recordLength','Max number of points',     SPV(100,'W','u32'),
    {LL:4,LH:1000000, SET:set_recordLength}],
['alarm',       'PV with alarm',            SPV(0,'WA'), {U:'du',**alarm}],
    ]

    # Templates for channel-related PVs. Important: SPV cannot be used in this list!
    ChannelTemplates = [
['c0$VoltsPerDiv',  'Vertical scale',       (1E-3,'W'), {U:'V/du'}],
#['c0$VoltOffset',  'Vertical offset',       (1E-3,), {U:'V/du'}],
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

#``````````````````Module constants
nPatterns = 100 # number of waveform patterns.
rng = np.random.default_rng(nPatterns)

#``````````````````Setter functions for PVs```````````````````````````````````
def set_recordLength(value):
    """Record length have changed. The tAxis should be updated accordingly."""
    printi(f'Setting tAxis to {value}')
    publish('tAxis', np.arange(value)*1.E-6)
    publish('recordLength', value)
    # Re-initialize noise array, because its size depends on recordLength
    set_noise(pvv('noiseLevel'))

def set_noise(level):
    """Noise level have changed. Update noise array."""
    v = float(level)
    recordLength = pvv('recordLength')
    ts = timer()

    pargs.noise = np.random.normal(scale=0.5*level, size=recordLength+nPatterns)# 45ms/1e6 points
    printi(f'Noise array[{len(pargs.noise)}] updated with level {v:.4g} V. in {timer()-ts:.4g} S.')
    publish('noiseLevel', level)

def set_externalControl(value):
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
    """Testing function. Do not use in production code."""
    set_recordLength(recordLength)
    #set_externalControl(pargs.prefix + pargs.external)

def poll():
    """Example of polling function"""
    #pattern = C_.cycle % nPatterns# produces sliding
    cycle = pvv('cycle')
    printv(f'cycle {repr(cycle)}')
    publish('cycle', cycle + 1)
    for ch in range(pargs.channels):
        pattern = rng.integers(0, nPatterns)
        chstr = f'c{ch+1:02}'
        wf = pargs.noise[pattern:pattern+pvv('recordLength')].copy()
        #print(f'ch{ch}, {pattern}: {wf[0], wf.sum(), wf.mean(), np.mean(wf)}')
        wf /= pvv(f'{chstr}VoltsPerDiv')
        #wf += pvv(f'{chstr}Offset')
        wf += ch
        publish(f'{chstr}Waveform', list(wf))
        publish(f'{chstr}Peak2Peak', np.ptp(wf))
        publish(f'{chstr}Mean', np.mean(wf))

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
# if pargs.list != '':
#     print('List of PVs:')
#     for _pvname in PVs:
#         print(_pvname)
printi(f'Hosting {len(PVs)} PVs')

# Initialize the device, using pargs if needed. 
# That can be used to set the number of points in the waveform, for example.
init(pargs.npoints)

# Start the Server. Use your set_server, if needed.
set_server('Start')

#``````````````````Main loop``````````````````````````````````````````````````
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
