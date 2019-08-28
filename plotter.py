import time
import sys
import numpy as np
from PIL import Image
import pyqtgraph as pg
import multiprocessing as mp
from scipy.signal import detrend

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

class PlotData():

    def __init__(self, data, channel_names, scoring_speed, acquisition_latency):

        self.channel_names = channel_names
        self.data = data
        self.stage = None 
        self.latency = 0
        self.acquisition_latency = acquisition_latency
        self.scoring_speed = scoring_speed
        self.confidence = 10
        self.t_now = 0
        self.sampling_rate = np.shape(data)[1]/30.0
        self.t = np.linspace(0,30, int(self.sampling_rate*30))
        self.N = np.shape(data)[0]

    def terminate(self):
        self.win.close()

    def info_text(self):
        if self.stage is None:
            return '<h2>Waiting for 60 sec buffer to fill up...</h2> \
                <h4>Scoring Every: %d sec, Scoring Latency: %5d ms <br /> \
                Acquisition Latency: %4d ms, time: %6d sec</h4>' \
                %(self.scoring_speed, self.latency, self.acquisition_latency, self.t_now)
        else:
            if self.confidence < 2.0:
                conf = 'Low'
                col = 'red'
            elif self.confidence < 4.0:
                conf = 'Medium'
                col = '#ffbf00'
            else:
                conf = 'High'
                col = 'green' 

            return '<h2>Sleep Stage <span style="background-color: #2b2301; color: #fff; \
                display: inline-block; padding: 3px 10px; font-weight: bold; border-radius: \
                5px;">%8s</span> &nbsp;&nbsp;&nbsp;Confidence <span style="background-color: %s; color: #fff; \
                display: inline-block; padding: 3px 10px; font-weight: bold; border-radius: 5px;">%5s</span></h2> \
                <h4>Scoring Every: %d sec, Scoring Latency: %5d ms <br /> \
                Acquisition Latency: %4d ms, time: %6d sec</h4>' \
                %(self.stage, col, conf, self.scoring_speed, self.latency, self.acquisition_latency, self.t_now)


    def call_back(self):

        if self.pipe.poll():
            command = self.pipe.recv()
            if command is None:
                self.terminate()
                return False
            else:
                self.data = command['data']
                self.stage = command['stage'] 
                self.confidence = command['confidence']
                self.latency = command['latency']
                self.t_now = command['t_now']
        
                self.txt.setHtml(self.info_text())

                for i in range(self.N):
                    self.plots[i].clear()
                    self.plots[i].setLimits(yMin = -100, yMax = 100)
                    self.plots[i].setLimits(xMin = -1, xMax = 31)
                    self.plots[i].getAxis('left').setTicks([[(-75,'-75'),(0,'0'),(75,'75')]])
                    self.plots[i].addLine(x=None, y=0, pen=pg.mkPen({'color':'c8c8c8'}, width=2))
                    self.plots[i].addLine(x=None, y=75, pen=pg.mkPen({'color':'c8c8c8'}, width=1, style=pg.QtCore.Qt.DashLine))
                    self.plots[i].addLine(x=None, y=-75, pen=pg.mkPen({'color':'c8c8c8'}, width=1, style=pg.QtCore.Qt.DashLine))
                    self.plots[i].plot(self.t, detrend(self.data[i,:]), pen=pg.mkPen(self.colors[i%5])) 

        pg.QtGui.QApplication.processEvents()
        return 0

    def __call__(self, pipe):

        print('starting plotter...')
        self.pipe = pipe
        self.win = pg.GraphicsWindow()
        self.win.setWindowTitle('Z3Score real-time scoring demo (c) Neurobit Technologies')
        self.win.resize(1000, 650)
        self.win.setBackground("w")
        self.sampling_rate = np.shape(self.data)[1]/30.0
        self.colors = [pg.mkColor(57,106,177), pg.mkColor(218,124,48), pg.mkColor(62,150,81), pg.mkColor(204,37,41), pg.mkColor(107,76,154)]
        self.plots = []
        for i in range(self.N):
            plt = self.win.addPlot(row=i+1, col=1, colspan=6)
            plt.setLimits(yMin = -100, yMax = 100)
            plt.setLimits(xMin = -1, xMax = 31)
            plt.setMouseEnabled(x=False, y=False)
            plt.setLabel('left', self.channel_names[i])
            plt.getAxis('left').setTicks([[(-75,'-75'),(0,'0'),(75,'75')]])
            self.plots.append(plt)

        for i in range(self.N):
            self.plots[i].addLine(x=None, y=0, pen=pg.mkPen({'color':'c8c8c8'}, width=2))
            self.plots[i].addLine(x=None, y=75, pen=pg.mkPen({'color':'c8c8c8'}, width=1, style=pg.QtCore.Qt.DashLine))
            self.plots[i].addLine(x=None, y=-75, pen=pg.mkPen({'color':'c8c8c8'}, width=1, style=pg.QtCore.Qt.DashLine))

        self.info = self.win.addViewBox(row=self.N+1,col=1,rowspan=5)
        self.logo = self.win.addViewBox(row=self.N+1,col=6)

        self.info.setAspectLocked()
        self.info.setMouseEnabled(x=False, y=False)

        self.img = pg.ImageItem(np.array(Image.open('logo.jpg')), axisOrder='row-major', autoDownsample=True)
        self.logo.invertY()
        self.logo.setAspectLocked()
        self.logo.addItem(self.img)
        self.logo.autoRange()
        self.logo.setMouseEnabled(x=False, y=False)
        self.logo.translateBy(x=-250,y=0)

        self.txt = pg.TextItem(border='r', color='k', anchor=(0.5,0.5))
        self.info.addItem(self.txt)

        self.txt.setHtml(self.info_text())
        self.txt.setTextWidth(450)
        self.info.setAspectLocked()
        self.info.autoRange()

        self.plots[0].setTitle('Showing latest 1 epoch (30 seconds) of Data')
        self.plots[-1].setLabel('bottom','Time (seconds)')

        self.timer = pg.QtCore.QTimer(self.win)

        self.timer.timeout.connect(self.call_back)
        self.timer.start(10)
        print('...done')
        
        if (sys.flags.interactive != 1) or not hasattr(pg.QtCore, 'PYQT_VERSION'):
            pg.QtGui.QApplication.instance().exec_()
        
        pg.QtGui.QApplication.processEvents()

    

channel_names = [
    'C3-A2 (uV)',
    'C4-A1 (uV)',
    'EOGL-A2 (uV)',
    'EOGR-A2 (uV)',
    'EMG (uV)'
]


if __name__ == '__main__':

    plot_pipe, plotter_pipe = mp.Pipe()
    send = plot_pipe.send

    plotter = PlotData(data = np.zeros((5,256*30)), 
            channel_names=channel_names, scoring_speed=3, acquisition_latency=50)

    plot_process = mp.Process(
            target=plotter, args=(plotter_pipe,))

    plot_process.start()
    
    for i in range(100):
        command ={} 
        command['data'] = np.random.randn(5,256*30)*10
        command['stage'] = 'NREM 1'
        command['confidence'] = 2.6
        command['latency'] = 50
        command['t_now'] = 50
        if not plotter_pipe.poll():
            send(command)
        time.sleep(0.010)

    send(None)
