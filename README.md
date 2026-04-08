# epicsdev

`epicsdev` is a small Python toolkit for building **EPICS PVAccess** servers with
[p4p](https://github.com/epics-base/p4p).

It is intended for fast development of simulated devices, instrument front ends,
and stress-test servers that publish scalars, waveforms, and images.

Background reading:
[Why Python-based servers are essential for large EPICS facility like future EIC](https://github.com/eicorg/docs/blob/master/python-development/epics_development_with_python_and_ai.md)

## What `epicsdev` provides

- A simple API for defining and hosting PVs
- Built-in IOC-style helper PVs for status and basic statistics
- Autosave/restore of writable PV values
- Optional logging of `put` operations to a separate PV
- Example applications for waveforms, images, and text logging

In practice, it combines a Python helper library with a few services commonly
expected from EPICS IOCs:

- **Autosave**: save writable PV values and restore them on restart
- **IOC-stats-style PVs**: host name, uptime, heartbeat, CPU load, and related PVs
- **Put logging**: optional forwarding of `put` activity to a logging PV

## Package contents

| Module | Purpose |
| --- | --- |
| `epicsdev.epicsdev` | Core helper functions for creating PVAccess servers |
| `epicsdev.imagegen` | Synthetic image generator for high-throughput testing |
| `epicsdev.putlog` | Text logger driven by a writable PV |
| `config/` | Example `pypeto` pages and a Phoebus display |

## Installation

Install the base package:

```bash
python -m pip install epicsdev
```

Optional tools for GUI pages and plotting:

```bash
python -m pip install pypeto pvplot
```

## Quick start

Start the built-in demo server:

```bash
python -m epicsdev.epicsdev
```

The demo uses the default PV prefix:

```text
epicsDev0:
```

### Open the example control page

```bash
python -m pypeto -c config -f epicsdev
```

This page gives you:

- basic server control
- live parameter monitoring
- waveform plotting helpers

Screenshots:

- [pypeto control page](docs/epicsdev_pypet.png)
- [pvplot example](docs/epicsdev_pvplot.jpg)

### Phoebus display

An example Phoebus display file is included at [config/epicsdev.bob](config/epicsdev.bob).
Screenshot: [Phoebus display](docs/phoebus_epicsdev.jpg)

## Minimal programming model

The typical workflow is:

1. define PVs
2. initialize the server with `init_epicsdev()`
3. start a `p4p.server.Server`
4. publish updates from your polling loop

PV definitions are lists with this shape:

```python
[name, description, initial_value, extra]
```

Where `extra` is optional and may include keys such as:

- `features`: PV features such as writable or discrete
- `type`: explicit EPICS type, for example `u32` or `f32`
- `units`: engineering units
- `limitLow`, `limitHigh`: write limits
- `setter`: callback invoked on writes
- `valueAlarm`: value alarm configuration

### Normative Type (NT) selection from `initial_value`

`epicsdev` selects the underlying PV normative type from `initial_value`
(unless overridden by `extra["type"]`).

Current behavior:

| `initial_value` | `features` | Chosen NT | Notes |
| --- | --- | --- | --- |
| NumPy `ndarray` | any | `NTNDArray` | Current implementation routes any NumPy array to `NTNDArray`. |
| list of choices | contains `D` | `NTEnum` | Value is stored as `{choices, index}`; initial index is 0. |
| scalar (`int`, `float`, `str`) | no `D` | `NTScalar` | Default scalar mappings: `int -> i32`, `float -> f32`, `str -> s`. |
| iterable (for example list/tuple) | no `D` | `NTScalarArray` | Element type is inferred from the first item. |

Type-code mapping follows p4p scalar codes (for example `i32`, `u32`, `f32`,
`f64`, `s8`, ...). You can force a specific type using `extra["type"]`.

Examples:

- `42` -> `NTScalar(i32)`
- `3.14` -> `NTScalar(f32)`
- `[1, 2, 3]` -> `NTScalarArray(i32)`
- `['OFF', 'ON']` with `{"features": "D"}` -> `NTEnum`
- `np.zeros((120, 120), dtype=np.int16)` -> `NTNDArray`

Notes:

- For discrete PVs (`D`), autosave stores the enum **index** rather than the
   choice text, so updated choice lists can still be restored predictably.
- For iterable non-NumPy values, keep the initial sequence non-empty so element
   type inference is unambiguous.

Minimal example:

```python
from p4p.server import Server
from epicsdev.epicsdev import init_epicsdev, publish, pvv, set_server, sleep

pv_defs = [
   ["temperature", "Simulated temperature", 25.0, {"features": "W", "units": "C"}],
   ["waveform", "Example waveform", [0.0], {"units": "V"}],
]

pvs = init_epicsdev("demo0:", pv_defs, verbose=1)
server = Server(providers=[pvs])
set_server("Start")

while True:
   publish("temperature", pvv("temperature") + 0.01)
   if not sleep():
      pass
```

## Example applications

### `epicsdev.imagegen`

`imagegen` generates synthetic 2D images with a grid of Gaussian blobs and
optional per-row PVs.

It publishes:

- a noisy image
- PVs that control image size, blob count, blob width, and noise level
- 10,000 of dynamicaly-changed waveform int16 PVs, each representing 1000-point row.
- The publishing performance is 55,000 of PVs per second (110 MB/s).

The generated data is intended for high-throughput testing of EPICS clients,
transport, and visualization tools.

[example](docs/using_imagegen.md)

### `epicsdev.putlog`

`putlog` hosts a writable PV named `dump` and appends received text to a file.

Start the logger:

```bash
python -m epicsdev.putlog /tmp/putlog.txt
```

By default, the logger prefix is:

```text
putlog0:
```

Write text to it with:

```bash
pvput putlog0:dump "hello from client"
```

## Notes on autosave and helper PVs

When you initialize a server with `init_epicsdev()`, `epicsdev` automatically
adds a standard set of helper PVs before your application-specific PVs. These
include PVs such as:

- `HOSTNAME`
- `VERSION`
- `HEARTBEAT`
- `UPTIME`
- `CPU_LOAD`
- `status`
- `server`
- `verbose`
- `sleep`
- `cycle`
- `cycleTime`

Writable PV values can be stored in an autosave file and restored on restart.
This makes `epicsdev` practical for interactive development and lab setups
where operator-tuned values should survive process restarts.

## AI-assisted device support workflow

`epicsdev` is intentionally small and explicit, which makes it convenient for
AI-assisted code generation and device support prototyping.

Typical workflow:

1. identify a device API or programming manual
2. define PVs and their setter callbacks
3. generate a first server implementation from an existing `epicsdev` example
4. review, test, and refine

One example built this way is
[epicsdev_tektronix](https://github.com/ASukhanov/epicsdev_tektronix).

## Requirements

- Python 3.7+
- `p4p>=4.2.2`
- `psutil`

Optional:

- `pypeto`
- `pvplot`
- Phoebus for `.bob` display files
