# Working with epicsdev.imagegen

Start epicsdev.imagegen for image generation with 10000*1000 pixels 
```bash
python -m epicsdev.imagegen -c -gr -s10000,1000
```

Start python interpreter in another terminal
```python
from p4p.client.thread import Context
import pyqtgraph as pg
iface = Context('pva')
imageView = pg.image(iface.get('image0:image').T, scale=(10,1))
def show():
     imageView.setImage(iface.get('image0:image').T, scale=(10,1))

iface.put('image0:blobSigmaY',400); show()
iface.put('image0:blobSigmaX',20); show()
iface.put('image0:nBlobsX',6); show()
iface.put('image0:noiseLevel',100); show()
```
Click ROI and position the region of interest.
Click Color gradient and select 'flame'.

[imageView](./imagegen.jpg)