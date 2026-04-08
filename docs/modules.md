# Runnable Modules

This page lists the main runnable programs in `epicsdev`.

## `epicsdev.epicsdev`

Core helper library with a built-in demo server.

Run:

```bash
python -m epicsdev.epicsdev
```

What it demonstrates:

- framework helper PVs (`server`, `status`, `sleep`, `cycle`, `cycleTime`, ...)
- scalar, waveform, and image PVs
- periodic publishing loop and autosave behavior

## `epicsdev.imagegen`

High-throughput image generator variant used for stress/performance testing.

Run:

```bash
python -m epicsdev.imagegen -gr -s 10000,1000
```

Notes:

- `-g r` publishes per-row waveform PVs (`row0`, `row1`, ...)
- `-g s` publishes row statistics (`mean*`, `std*`, `peak2peak*`)

## `epicsdev.putlog`

Text logger server: writable PV `dump`; each received value is appended to a
log file.

Run:

```bash
python -m epicsdev.putlog /tmp/putlog.txt
```

Default writable PV name:

```text
putlog:dump
```

Example write:

```bash
pvput putlog:dump "hello from client"
```
