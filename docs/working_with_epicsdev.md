# Working with epicsdev.imagegen

Start epicsdev.imagegen for image generation with 10000*1000 pixels 
```python
python -m epicsdev.imagegen -c -gr -s10000,1000
```

Start python interpreter in another terminal
```python
from p4p.client.thread import Context
import pyqtgraph as pg
iface = Context('pva')
def show():
    arr=iface.get('image0:image')
    pg.image(arr.T)

show()

iface.put('image0:noiseLevel',100)
iface.put('image0:blobSigmaY',400)
iface.put('image0:blobSigmaX',20)
iface.put('image0:nBlobsX',6

show()
```
Click ROI and position the region of interest.

