import pyedflib
import numpy as np
from time import time, sleep

# This is a fake DataServer class, instead of reading data from an actual source in realtime 
# it reads it from a file offline. it behaves just like any other real-time Server.
# The buffer_size defines the duration of data that can be read on every call to read_buffer
# Usually the buffer_size is very small: 20 to 50 milli-seconds, it also means that if you do not 
# make the calls in time a buffer overflow happens and you miss some data. For example, if 
# buffer_size is 50 ms, call to read_buffer must be made within 50 ms, a warning will be 
# printed otherwise and data packets will be lost.

class DataServer:

    def __init__(self, buffer_size=500):
        
        # read data from local file
        path = 'sample_short.edf'
        edf_file = pyedflib.EdfReader(path)
        samples = edf_file.getNSamples()

        # For the sample data, these are the channel labels
        # 8. EOGl:A2, 9. EOGr:A1, 0. C3:A2, 1. C4:A1, 6. EMG
        # sampling rate of the data is 256 Hz

        self.total_samples = samples[0]
        self.data = np.empty([5,self.total_samples])
        self.sampling_rate  = edf_file.getSampleFrequency(0)
        # C3-A2
        self.data[0,:] = np.asarray(edf_file.readSignal(0))
        # C4-A1
        self.data[1,:] = np.asarray(edf_file.readSignal(1))
        # EOG-L-A2
        self.data[2,:] = np.asarray(edf_file.readSignal(8))
        # EOG-R-A1
        self.data[3,:] = np.asarray(edf_file.readSignal(9))
        # chin-EMG
        self.data[4,:] = np.asarray(edf_file.readSignal(6))
       
        # No of samples to read each time
        self.buffer_size = buffer_size
        self.buffer_samples = int(buffer_size*256.0/1000)
        self.current_location = 0
        self.last_call_time = None
        edf_file._close()

    def read_buffer(self, realistic=True):
        if self.current_location == 0:
            if self.current_location + self.buffer_samples >= self.total_samples:
                print('Data stream ended.')
                return None
            
            self.last_call_time = time()
            buffer = self.data[:,self.current_location:self.current_location+self.buffer_samples]
            self.current_location += self.buffer_samples
            return buffer
        
        delta = time() - self.last_call_time
        if delta*1000 > self.buffer_size:
            print('Warning: buffer overflow - data samples are lost.')
            self.current_location += int((delta*1000 - self.buffer_size)*self.sampling_rate/1000)
        
        if self.current_location + self.buffer_samples >= self.total_samples:
            print('Data stream terminated.')
            return None

        buffer = self.data[:,self.current_location:self.current_location+self.buffer_samples]
        self.current_location += self.buffer_samples

        wait_time = self.buffer_size - delta*1000 
        if realistic and wait_time > 0.0:
            sleep(wait_time/1000)

        self.last_call_time = time()
        return buffer


