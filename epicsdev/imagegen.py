"""EPICS image generator based on epicsdev.

Hosts PVs controlling image size, Gaussian blob grid, and noise, and publishes
an int16 2D image to the `image` PV.
"""
__version__= 'v0.0.2 26-03-28'# added row PVs, periodic performance metrics printout, and some refactoring.
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

DEFAULT_NBLOBS_X = 4
DEFAULT_NBLOBS_Y = 4
DEFAULT_BLOB_MAX = 1000
DEFAULT_BLOB_SIGMA = 4.0
DEFAULT_NOISE_LEVEL = 10.0

RNG = np.random.default_rng()

#``````````````````Module attributes
ElapsedTime = {'blur': 0., 'publish': 0., 'poll': 0.}
class C_():
    cyclesSinceUpdate = 0
    image = None

def blurred(noise_level,image):
    """Return blurred image with additive noise."""
    if noise_level > 0:
        image += RNG.normal(0.0, noise_level, size=image.shape).astype(np.int16)#astype(np.float32)
    return image

def _gaussian_blob_grid_image() -> np.ndarray:
    """Build image with a regular grid of Gaussian blobs."""
    n_rows = int(pvv("nRows"))
    n_cols = int(pvv("nCols"))
    n_blobs_x = int(pvv("nBlobsX"))
    n_blobs_y = int(pvv("nBlobsY"))
    blob_max = float(pvv("blobMax"))
    sigma = float(pvv("blobSigma"))
    noise_level = float(pvv("noiseLevel"))

    yy, xx = np.indices((n_rows, n_cols), dtype=np.float32)
    image = np.zeros((n_rows, n_cols), dtype=np.float32)

    dx = n_cols / (n_blobs_x)/2 if n_blobs_x > 0 else n_cols
    dy = n_rows / (n_blobs_y)/2 if n_blobs_y > 0 else n_rows
    if n_blobs_x > 0 and n_blobs_y > 0 and blob_max > 0:
        x_centers = np.linspace(dx, n_cols - dx, n_blobs_x, dtype=np.float32)
        y_centers = np.linspace(dy, n_rows - dy, n_blobs_y, dtype=np.float32)
        print(f"Blob centers X: {x_centers}, Y: {y_centers}")

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

    image = np.clip(image, 0, np.iinfo(np.int16).max)
    return image.astype(np.int16)

def publish_image() -> None:
    """Recompute and publish image from current parameter PVs."""
    C_.image = _gaussian_blob_grid_image()
    image = blurred(pvv("noiseLevel"), C_.image)
    publish("image", image)
    for row in range(min(pargs.nrows, image.shape[0])):
        publish(f"row{row}", image[row])

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
    pvdefs = [
        ["nRows","Number of rows in the image",pargs.nrows,
            {F: "W", T: "u32", LL: 10, LH: 10000, SET: _set_int_and_regenerate},],
        ["nCols","Number of columns in the image",pargs.ncols,
            {F: "W", T: "u32", LL: 100, LH: 1000, SET: _set_int_and_regenerate},],
        ["nBlobsX","Number of blobs along X axis", DEFAULT_NBLOBS_X,
            {F: "W", T: "u8", LL: 0, LH: 10, SET: _set_int_and_regenerate},],
        ["nBlobsY","Number of blobs along Y axis", DEFAULT_NBLOBS_Y,
            {F: "W", T: "u8", LL: 0, LH: 10, SET: _set_int_and_regenerate},],
        ["blobMax","Blob maximum", DEFAULT_BLOB_MAX,
            {F: "W", T: "u32", LL: 0, LH: 65535, SET: _set_int_and_regenerate},],
        ["blobSigma","Blob sigma", DEFAULT_BLOB_SIGMA,
            {F: "W", T: "f32", LL: 0.0, LH: 1000.0, SET: _set_float_and_regenerate},],
        ["noiseLevel","Noise level", DEFAULT_NOISE_LEVEL,
            {F: "W", T: "f32", LL: 0.0, LH: 1000.0, SET: _set_float_and_regenerate},],
        ["image","Image",np.zeros((pargs.nrows, pargs.ncols), dtype="int16"),],
    ]
    for row in range(pargs.nrows):
        pvdefs.append([f"row{row}", f"Row {row} of the image", 
                       np.ones(pargs.ncols, dtype="int16")*row])
    return pvdefs

def periodic_update():
    """Perform periodic update"""
    printi(f'Elapsed times during last {C_.cyclesSinceUpdate} cycles: {ElapsedTime}')
    C_.cyclesSinceUpdate = 0
    for key in ElapsedTime:
        ElapsedTime[key] = 0.

def poll():
    """Device polling function, called every cycle when server is running"""
    C_.cyclesSinceUpdate += 1
    ts0 = timer()
    image = blurred(pvv("noiseLevel"), C_.image)
    ElapsedTime['blur'] += timer() - ts0
    for row in range(min(pargs.nrows, image.shape[0])):
        ts1 = timer()
        publish(f"row{row}", image[row])
        ElapsedTime['publish'] += timer() - ts1
    ElapsedTime['poll'] += timer() - ts0

#``````````````````Argument parsing
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog=f'{__version__}'
)
parser.add_argument("-a", "--autosave", nargs="?", default="")
parser.add_argument("-c", "--recall", action="store_false")
parser.add_argument("-d", "--device", default="image")
parser.add_argument("-i", "--index", default="0")
parser.add_argument("-l", "--list", nargs="?")
parser.add_argument("-s", "--shape", default="120,120", help=
    "Initial number of rows and columns in the image."  )
parser.add_argument("-p", "--putlogPV", default="putlog:dump")
parser.add_argument("-v", "--verbose", action="count", default=0)
pargs = parser.parse_args()
pargs.nrows, pargs.ncols = [int(s) for s in pargs.shape.split(',')]

prefix = f"{pargs.device}{pargs.index}:"
pvs = init_epicsdev(
    prefix,
    my_pv_defs(),
    pargs.verbose,
    None,
    pargs.list,
    pargs.autosave,
    pargs.recall,
    pargs.putlogPV,
)

publish_image()
set_server("Start")

server = Server(providers=[pvs])
printi(f"Server started. Sleeping per cycle: {repr(pvv('sleep'))} S.")

while True:
    state = serverState()
    if state.startswith("Exit"):
        break
    if not state.startswith('Stop'):
        poll()
    if not sleep():# Sleep and update performance metrics periodically
        periodic_update()

printi("Server exited")