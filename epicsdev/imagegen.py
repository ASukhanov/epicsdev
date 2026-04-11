"""EPICS image generator based on epicsdev.
Generates an image with a grid of noisy Gaussian blobs, with parameters 
defined by PVs. 
The image is recomputed and published when the parameters are changed via PVs. 
Random normal noise is added to the image on each update, without changing 
the underlying blob pattern.
PVs representing image rows and statistics PVs are updated periodically.
"""
# pylint: disable=invalid-name
__version__= 'v0.1.1 26-04-11'# gridCsalex sclales image with respect to the center of the image

from time import perf_counter as timer
import argparse
import numpy as np

from epicsdev.epicsdev import (
    Server,
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
RNG = np.random.default_rng()

#``````````````````Module attributes
ElapsedTime = {'blur': 0., 'publish': 0., 'poll': 0.}
class C_():
    cyclesSinceUpdate = 0
    image = None

def blurred(noise_level, image):
    """Return blurred image with additive noise."""
    if noise_level > 0:
        imageOut = image + RNG.normal(0.0, noise_level, size=image.shape)
    else:
        imageOut = image
    return imageOut.astype(np.int16)

def _gaussian_blob_grid_image() -> np.ndarray:
    """Build image with a regular grid of Gaussian blobs."""
    n_rows = int(pvv("nRows"))
    n_cols = int(pvv("nCols"))
    n_blobs_x = int(pvv("nBlobsX"))
    n_blobs_y = int(pvv("nBlobsY"))
    blob_max = float(pvv("blobMax"))
    sigmax = float(pvv("blobSigmaX"))
    sigmay = float(pvv("blobSigmaY"))

    yy, xx = np.indices((n_rows, n_cols), dtype=np.float32)
    image = np.zeros((n_rows, n_cols), dtype=np.float32)

    dx = n_cols / (n_blobs_x)/2 if n_blobs_x > 0 else n_cols
    dy = n_rows / (n_blobs_y)/2 if n_blobs_y > 0 else n_rows
    if n_blobs_x > 0 and n_blobs_y > 0 and blob_max > 0:
        x_centers = pvv('gridScaleX') * np.linspace(dx, n_cols - dx, n_blobs_x, dtype=np.float32)
        print(f"Blob centers X before scaling: {x_centers}")
        x_centers += n_cols/2. * (1 - pvv('gridScaleX')) # Scale centers with respect to the center of the image
        print(f"Blob centers X after scaling: {x_centers}")
        y_centers = np.linspace(dy, n_rows - dy, n_blobs_y, dtype=np.float32)
        print(f"Blob centers X: {x_centers}, Y: {y_centers}")

        for cx in x_centers:
            for cy in y_centers:
                r2 = (xx - cx) ** 2 / (sigmax * sigmax) + (yy - cy) ** 2 / (sigmay * sigmay)
                image += blob_max * np.exp(-r2)
    return image

def publish_image() -> None:
    """Recompute and publish image from current parameter PVs."""
    C_.image = _gaussian_blob_grid_image()
    image = blurred(pvv("noiseLevel"), C_.image)

    publish("image", image)
    if 'r' in pargs.generate:
        for row in range(min(pargs.nrows, image.shape[0])):
            publish(f"row{row}", image[row])

def _set_and_regenerate(value, spv):
    """Generic setter that also rebuilds image."""
    publish(spv.name, value)
    publish_image()

def my_pv_defs():
    """Application PV definitions."""
    pvdefs = [
["nRows","Number of rows in the image",pargs.nrows,
            {F: "W", LL: 1, LH: 100000, SET: _set_and_regenerate},],
["nCols","Number of columns in the image",pargs.ncols,
            {F: "W", LL: 10, LH: 1000000, SET: _set_and_regenerate},],
["nBlobsX","Number of blobs along X axis", 4,
            {F: "W", LL: 0, LH: 100, SET: _set_and_regenerate},],
["nBlobsY","Number of blobs along Y axis", 4,
            {F: "W", LL: 0, LH: 100, SET: _set_and_regenerate},],
["blobMax","Blob maximum", 1000,
            {F: "W", LL: 0, LH: 65535, SET: _set_and_regenerate},],
["blobSigmaX","Blob sigma X", 4.0,
            {F: "W", LL: 0.1, LH: 1000.0, SET: _set_and_regenerate},],
["blobSigmaY","Blob sigma Y", 4.0,
            {F: "W", LL: 0.1, LH: 1000.0, SET: _set_and_regenerate},],
["noiseLevel","Noise level", 10.0,
            {F: "W", LL: 0.0, LH: 1000.0, SET: _set_and_regenerate},],
["gridScaleX","Scale of the horizontal grid of blobs", 1.0, {F: "W", SET: _set_and_regenerate},],
["image","Image",np.zeros((pargs.nrows, pargs.ncols), dtype="int16"),],
    ]
    for row in range(pargs.nrows):
        if 'r' in pargs.generate:
            pvdefs.append(
[f"row{row}", f"Row {row} of the image", 
                    np.zeros(pargs.ncols, dtype="int16")*row])
        if 's' in pargs.generate:
            pvdefs.extend([
[f'mean{row}', f'Mean of rows {row}',0.0],
[f'std{row}', f'Standard deviation of rows {row}', 0.0],
[f'peak2peak{row}', f'Peak-to-peak of rows {row}', 0.0],
                ])
    return pvdefs

def periodic_update():
    """Perform periodic update"""
    printi(f'Elapsed times during last {C_.cyclesSinceUpdate} cycles: {[(name, round(v,4)) for name, v in ElapsedTime.items()]}')
    C_.cyclesSinceUpdate = 0
    for key in ElapsedTime:
        ElapsedTime[key] = 0.

def poll():
    """Device polling function, called every cycle when server is running.
    Recompute image and publish row PVs and statistics periodically
    """
    C_.cyclesSinceUpdate += 1
    ts0 = timer()
    image = blurred(pvv("noiseLevel"), C_.image)
    ElapsedTime['blur'] += timer() - ts0
    for row in range(min(pargs.nrows, image.shape[0])):
        ts1 = timer()
        if 'r' in pargs.generate:
            publish(f"row{row}", image[row])
        if 's' in pargs.generate:
            publish(f'mean{row}', np.mean(image[row]))
            publish(f'std{row}', np.std(image[row]))
            publish(f'peak2peak{row}', np.ptp(image[row]))
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
parser.add_argument("-g", "--generate", nargs="?", default="", help=
    "Generate array PVs on startup: 'r' for row, 's' for statistics'"                    )
parser.add_argument("-i", "--index", default="0")
parser.add_argument("-s", "--shape", default="120,120", help=
    "Initial number of rows and columns in the image."  )
parser.add_argument("-p", "--putlogPV", default="putlog:dump")
parser.add_argument("-v", "--verbose", action="count", default=0)
pargs = parser.parse_args()
pargs.nrows, pargs.ncols = [int(s) for s in pargs.shape.split(',')]
printi(f"Parsed arguments: {pargs}")

prefix = f"{pargs.device}{pargs.index}:"
pvs = init_epicsdev(
    prefix,
    my_pv_defs(),
    pargs.verbose,
    None,
    None,
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
