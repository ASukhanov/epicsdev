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
the EPICS environment. For example the following command will generate 10000 of 
100-point noisy waveforms and 40000 of scalar parameters per second.
```
python -m epicsdev.multiadc -s0.1 -c10000 -n100
```
The GUI for monitoring:<br>
```python -m pypeto -c config -f multiadc```

The graphs should look like this: 
[control page](docs/epicsdev_pypet.png),
[plots](docs/epicsdev_pvplot.jpg).

Example of [Phoebus display](docs/phoebus_epicsdev.jpg), as defined in config/epicsdev.bob.

## Using AI to generate PVAccess server for arbitrary instruments.
The epicsdev module is designed to be suitable for automatic development using AI agents.<br>
The roadmap to create a server for new instrument using copilot at github:
- Create new repository.
- In the prompt section enter something like this:<br>
'Build device support for Tektronix MSO oscilloscopes using epicsdev_rigol_scope as a template and programming manual at < link to a pdf file >.'
- In 20-40 minutes the copilot will create a pull request.
- Follow instructions to review, commit and merge.

As an example, the generated server for Tektronix MSO oscilloscope was 99% correct and it reqiured very minor modifications.


