# epicsdev

Helper module for building **EPICS PVAccess servers** using [p4p](https://github.com/epics-base/p4p).

`epicsdev` is designed for:

* Rapid PVAccess server development
* High-rate data simulation and stress testing
* GUI-based monitoring and control
* AI-assisted automatic device support generation

---

## Installation

```bash
python -m pip install epicsdev
```

---

## Quick Demo

Start the demo PVAccess server:

```bash
python -m epicsdev.epicsdev
```

---

## Control & Visualization

Install optional GUI and plotting tools:

```bash
python -m pip install pypeto pvplot
```

Launch the control interface:

```bash
python -m pypeto -c config -f epicsdev
```

This provides:

* Device control panel
* Live waveform plots
* Real-time parameter monitoring

---

# Multi-Channel Waveform Generator

`epicsdev.multiadc` generates high-throughput synthetic data for stress-testing EPICS systems.

### Example

Generate:

* **10,000** noisy waveforms per second
* **100 points per waveform**
* **40,000 scalar parameters per second**

```bash
python -m epicsdev.multiadc -s 0.1 -c 10000 -n 100
```

### Monitoring GUI

```bash
python -m pypeto -c config -f multiadc
```

The GUI includes:

* Control page
* Real-time waveform plots<br>
The screenshots can be seen here: [control page](docs/epicsdev_pypet.png), [plots](docs/epicsdev_pvplot.jpg).
---

## Phoebus Display

An example Phoebus display is provided:

```
config/epicsdev.bob<br>
```
---
[Screenshot](docs/phoebus_epicsdev.jpg)

# AI-Assisted Device Support Development

`epicsdev` is structured to enable automated server generation using AI tools such as GitHub Copilot.

## Workflow Example

1. Create a new GitHub repository.

2. Provide an AI prompt such as:

   ```
   Build device support for Tektronix MSO oscilloscopes 
   using epicsdev_rigol_scope as a template and the 
   programming manual available at <PDF link>.
   ```

3. Within ~20–40 minutes, the AI can generate a pull request.

4. Review, test, make minor corrections if needed, then merge.

### Real-World Example

Using this method, a server implementation for a **Tektronix MSO oscilloscope** was:

* ~99% correct on first generation
* Required only minor adjustments

---

# Use Cases

* EPICS PVAccess server prototyping
* High-rate data simulation
* Control system stress testing
* Rapid instrument integration
* AI-driven device support generation

---

# Requirements

* Python 3.8+
* p4p 4.2.2+
* EPICS PVAccess environment

Optional:

* pypeto
* pvplot
* Phoebus (for .bob display files)

---
