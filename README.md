# epicsdev
Helper module for creating EPICS PVAccess servers.

Demo:
```
python pip install epicsdev
python -m epicsdev.epicsdev
```

To control and plot:
```
python pip install pypeto,pvplot
python -m pypeto -c config -f epicsdev
```

## Multi-channel waveform generator
Module **epicdev.multiadc** can generate large amount of data for stress-testing
the EPICS environment. For example the following command will generate 100 of 
1000-pont noisy waveforms and 300 of scalar parameters.
```
python -m epicsdev.multiadc -c100 -n1000
```
The GUI for monitoring:<br>
```python -m pypeto -c config -f multiadc```

The graphs should look like this: 
[control page](docs/epicsdev_pypet.png),
[plots](docs/epicsdev_pvplot.jpg).


