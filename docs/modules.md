# Runnable Modules

This page lists the main runnable programs in `epicsdev`.

## `epicsdev.epicsdev`

Generic/demo PVAccess server framework.

Run:

```bash
python -m epicsdev.epicsdev
```

## `epicsdev.multiadc`

Multi-channel waveform generator for load and stress testing.

Run:

```bash
python -m epicsdev.multiadc
```

## `epicsdev.putlog`

Hosts writable PV `dump`; every value written to it is appended to a file.

Run:

```bash
python -m epicsdev.putlog /tmp/putlog.txt
```

Default writable PV name:

```text
putlog0:dump
```

Example write:

```bash
caput -p pva putlog0:dump "hello from client"
```
