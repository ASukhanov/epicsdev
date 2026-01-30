"""Pypet page for epicdev.multiadc module"""
# format: pypeto 1.2+
__version__ = 'v0.0.1 2026-01-23'#
print(f'epicsScope {__version__}')

#``````````````````Definitions````````````````````````````````````````````````
# python expressions and functions, used in the spreadsheet
_ = ''
def span(x,y=1): return {'span':[x,y]}
def color(*v): return {'color':v[0]} if len(v)==1 else {'color':list(v)}
def font(size): return {'font':['Arial',size]}
def just(i): return {'justify':{0:'left',1:'center',2:'right'}[i]}
def slider(minValue,maxValue):
    """Definition of the GUI element: horizontal slider with flexible range"""
    return {'widget':'hslider','opLimits':[minValue,maxValue],'span':[2,1]}

LargeFont = {'color':'light gray', **font(18), 'fgColor':'dark green'}
ButtonFont = {'font':['Open Sans Extrabold',14]}# Comic Sans MS
LYRow = {'ATTRIBUTES':{'color':'light yellow'}}
lColor = color('lightGreen')

# definition for plotting cell
PyPath = 'python -m'
PaneP2P = ' '.join([f'c{i+1:02d}Mean c{i+1:02d}Peak2Peak' for i in range(1)])
PaneWF = ' '.join([f'c{i+1:02d}Waveform' for i in range(1)])
#PaneT = 'timing[1] timing[3]'
Plot = {'Plot':{'launch':
  f'{PyPath} pvplot Y-5:5 -aV:multiadc0: -#0"{PaneP2P}" -#1"{PaneWF}"',# -#2"{PaneT}"',
  **lColor, **ButtonFont}}
print(f'Plot command: {Plot}')
#``````````````````PyPage Object``````````````````````````````````````````````
class PyPage():
    def __init__(self, instance='multiadc0:',
            title="Simulated oscilloscope", channels=6):
        """instance: unique name of the page.
        For EPICS it is usually device prefix 
        """
        print(f'Instantiating Page {instance,title} with {channels} channels')

        #``````````Mandatory class members starts here````````````````````````
        self.namespace = 'PVA'
        self.title = title

        #``````````Page attributes, optional`````````````````````````
        self.page = {**color(240,240,240)}
        #self.page['editable'] = False

        #``````````Definition of columns`````````````````````````````
        self.columns = {
            1: {'width': 120, 'justify': 'right'},
            2: {'width': 80},
            3: {'width': 80, 'justify': 'right'},
            4: {'width': 80},
            5: {'width': 80, 'justify': 'right'},
            6: {'width': 80},
            7: {'width': 80},
            8: {'width': 80},
            9: {'width': 80},
        }
        """`````````````````Configuration of rows`````````````````````````````
A row is a list of comma-separated cell definitions.
The cell definition is one of the following: 
  1)string, 2)device:parameters, 3)dictionary.
The dictionary is used when the cell requires extra features like color, width,
description etc. The dictionary is single-entry {key:value}, where the key is a 
string or device:parameter and the value is dictionary of the features.
        """
        D = instance

        #``````````Abbreviations, used in cell definitions
        def ChLine(suffix):
            return [f'{D}c{ch+1:02d}{suffix}' for ch in range(channels)]
        #FOption = ' -file '+logreqMap.get(D,'')
        #``````````mandatory member```````````````````````````````````````````
        self.rows = [
['Device:', D, {D+'version':span(2,1)},_, 'host:', D+'host',_],
['State:', D+'server','cycle:', D+'cycle',_,_,Plot], # 'Recall:', D+'setup',],
['Status:', {D+'status': span(8,1)}],
['Polling Interval:', D+'polling', 'nPoints:', D+'recordLength',
	'Noise:', D+'noiseLevel',_],
[{'ATTRIBUTES':{**color('lightCyan'),**just(1)}},
	'Channels:','CH1','CH2','CH3','CH4','CH5','CH6'],
['V/div:']+ChLine('VoltsPerDiv'),
['Mean:']+ChLine('Mean'),
['Peak2Peak:']+ChLine('Peak2Peak'),
#['Waveform:']+ChLine('Waveform'),
        ]
