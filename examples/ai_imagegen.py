"""EPICS image generator based on epicsdev.

Hosts PVs controlling image size, Gaussian blob grid, and noise, and publishes
an int16 2D image to the `image` PV.
"""

import argparse
from time import perf_counter as timer

import numpy as np
from p4p.server import Server

from epicsdev.epicsdev import (
    init_epicsdev,
    printi,
    publish,
    pvv,
    serverState,
    set_server,
    sleep,
)


F = "features"
T = "type"
U = "units"
LL = "limitLow"
LH = "limitHigh"
SET = "setter"

DEFAULT_NROWS = 10
DEFAULT_NCOLS = 100
DEFAULT_NBLOBS_X = 4
DEFAULT_NBLOBS_Y = 4
DEFAULT_BLOB_MAX = 1000
DEFAULT_BLOB_SIGMA = 4.0
DEFAULT_NOISE_LEVEL = 10.0

RNG = np.random.default_rng()


def _gaussian_blob_grid_image() -> np.ndarray:
    """Build image with a regular grid of Gaussian blobs and additive noise."""
    n_rows = int(pvv("nRows"))
    n_cols = int(pvv("nCols"))
    n_blobs_x = int(pvv("nBlobsX"))
    n_blobs_y = int(pvv("nBlobsY"))
    blob_max = float(pvv("blobMax"))
    sigma = float(pvv("blobSigma"))
    noise_level = float(pvv("noiseLevel"))

    yy, xx = np.indices((n_rows, n_cols), dtype=np.float32)
    image = np.zeros((n_rows, n_cols), dtype=np.float32)

    if n_blobs_x > 0 and n_blobs_y > 0 and blob_max > 0:
        x_centers = np.linspace(0, n_cols - 1, n_blobs_x, dtype=np.float32)
        y_centers = np.linspace(0, n_rows - 1, n_blobs_y, dtype=np.float32)

        if sigma <= 0:
            for cx in x_centers:
                for cy in y_centers:
                    image[int(round(cy)), int(round(cx))] += blob_max
        else:
            denom = 2.0 * sigma * sigma
            for cx in x_centers:
                for cy in y_centers:
                    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
                    image += blob_max * np.exp(-r2 / denom)

    if noise_level > 0:
        image += RNG.normal(0.0, noise_level, size=image.shape).astype(np.float32)

    image = np.clip(image, 0, np.iinfo(np.int16).max)
    return image.astype(np.int16)


def publish_image() -> None:
    """Recompute and publish image from current parameter PVs."""
    publish("image", _gaussian_blob_grid_image())


def _set_int_and_regenerate(value, spv):
    """Setter for integer controls that also rebuilds image."""
    publish(spv.name, int(value))
    publish_image()


def _set_float_and_regenerate(value, spv):
    """Setter for float controls that also rebuilds image."""
    publish(spv.name, float(value))
    publish_image()


def my_pv_defs():
    """Application PV definitions."""
    return [
        [
            "nRows",
            "Number of rows in the image",
            DEFAULT_NROWS,
            {F: "W", T: "u32", LL: 10, LH: 10000, SET: _set_int_and_regenerate},
        ],
        [
            "nCols",
            "Number of columns in the image",
            DEFAULT_NCOLS,
            {F: "W", T: "u32", LL: 100, LH: 1000, SET: _set_int_and_regenerate},
        ],
        [
            "nBlobsX",
            "Number of blobs along X axis",
            DEFAULT_NBLOBS_X,
            {F: "W", T: "u8", LL: 0, LH: 10, SET: _set_int_and_regenerate},
        ],
        [
            "nBlobsY",
            "Number of blobs along y axis",
            DEFAULT_NBLOBS_Y,
            {F: "W", T: "u8", LL: 0, LH: 10, SET: _set_int_and_regenerate},
        ],
        [
            "blobMax",
            "Blob maximum",
            DEFAULT_BLOB_MAX,
            {F: "W", T: "u32", LL: 0, LH: 65535, SET: _set_int_and_regenerate},
        ],
        [
            "blobSigma",
            "Blob sigma",
            DEFAULT_BLOB_SIGMA,
            {F: "W", T: "f32", LL: 0.0, LH: 1000.0, SET: _set_float_and_regenerate},
        ],
        [
            "noiseLevel",
            "Noise level",
            DEFAULT_NOISE_LEVEL,
            {F: "W", T: "f32", LL: 0.0, LH: 1000.0, SET: _set_float_and_regenerate},
        ],
        [
            "image",
            "Image",
            np.zeros((DEFAULT_NROWS, DEFAULT_NCOLS), dtype="int16"),
        ],
    ]


def periodic_update(_sum):
    """Publish update rate metrics."""
    if _sum["time"] <= 0:
        return
    updates_per_second = _sum["updates"] / _sum["time"]
    publish("throughput", round(updates_per_second, 6))
    _sum["updates"] = 0
    _sum["time"] = 0.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-a", "--autosave", nargs="?", default="")
    parser.add_argument("-c", "--recall", action="store_false")
    parser.add_argument("-d", "--device", default="image")
    parser.add_argument("-i", "--index", default="0")
    parser.add_argument("-l", "--list", nargs="?")
    parser.add_argument("-p", "--putlogPV", default="putlog:dump")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    prefix = f"{args.device}{args.index}:"
    pvs = init_epicsdev(
        prefix,
        my_pv_defs(),
        args.verbose,
        None,
        args.list,
        args.autosave,
        args.recall,
        args.putlogPV,
    )

    publish_image()
    set_server("Start")

    server = Server(providers=[pvs])
    printi(f"Server started. Sleeping per cycle: {repr(pvv('sleep'))} S.")

    _sum = {"updates": 0, "time": 0.0}
    while True:
        state = serverState()
        if state.startswith("Exit"):
            break
        if not state.startswith("Stop"):
            ts = timer()
            publish_image()
            _sum["time"] += timer() - ts
            _sum["updates"] += 1
        if not sleep():
            periodic_update(_sum)

    printi("Server exited")


if __name__ == "__main__":
    main()