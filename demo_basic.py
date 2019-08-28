#!/usr/bin/python
# Reference code for real-time sleep staging and intervention
# This is a very basic example to demonstrate the principles of real
# time scoring and intervention
# Prerequisites: Basic knowledge of Python, REST API
# 
#
# tested on Python 3.6 on Windows platform
# requires these python libraries:
# pycfslib, pyedflib, pebble, pillow, requests, numpy, sklearn and scipy
# 
#
# (c)-2019 Neurobit Technologies Pte Ltd Singapore
# https://www.neurobit.io
#
# protected by copyright law and international treaties
# Licensed under Neurobit End User License Agreement (EULA)
# Strictly for academic, research and non-commercial use only
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import csv
import warnings
import pyedflib
import numpy as np
from time import time
from requests import post
from sklearn.metrics import cohen_kappa_score
from pycfslib import create_stream_v2 as stream_data

# Ignore any warnings - You may want to remove this line
warnings.filterwarnings("ignore")

# Login information for Z3Score
# Note that real-time module is only available on V2 of the API
# Always use https instead of http to ensure security
server_url = 'https://z3score.com/api/v2'
# Do not have a key? Request one from contact@neurobit.io
email = 'demo@neurobit.io'
key = 'YourAccessKey'

# Sleep stages are encoded as:
stage_keys = {
    0: 'Wake',
    1: 'NREM 1',
    2: 'NREM 2',
    3: 'NREM 3',
    5: 'REM',
    9: 'Unknown',
} 

# Channel Names for our fake data server
channel_names = [
    'C3-A2 (uV)',
    'C4-A1 (uV)',
    'EOGL-A2 (uV)',
    'EOGR-A2 (uV)',
    'EMG (uV)'
]

# You need an authorization token to access the real-time module
# Use your login details to request it. The token auto expires after 16 hours
# Log in is a slow process, authorization tokens are a fast way to allow access to services 
# Note: you need special previlages to access the real-time module
try:
    response = post(server_url+'/get-token', data={'email':email, 'key':key})
except:
    print("Error communicating with server")
    exit(0)

if response.status_code != 200:
    print("Error communicating with server")
    exit(0)

data = response.json()
token = data['token']

if data['token'] == 0:
    print("Could not generate access token")
    print(data['message'])
    exit(0)

print("Access token generated for real-time module...")
print(data['message'])

# lets read all the data from sample.edf and store it in an array
path = 'sample.edf'
edf_file = pyedflib.EdfReader(path)

# for the sample data, these are the channel index
channel_no ={
    'C3': 0,
    'C4': 1,
    'EOGL': 8,
    'EOGR': 9,
    'EMG': 6
}

# for the sample data, sampling rate is same across all channels
samplig_rate = edf_file.getSampleFrequency(channel_no['C3'])

# find total epochs
samples = edf_file.getNSamples()
total_epochs = int(samples[channel_no['C3']]/samplig_rate/30)

# read all the data and store it in a Numpy array
data = np.empty([5,samples[channel_no['C3']]])
# C3-A2
data[0,:] = np.asarray(edf_file.readSignal(channel_no['C3']))
# C4-A1
data[1,:] = np.asarray(edf_file.readSignal(channel_no['C4']))
# EOG-L-A2
data[2,:] = np.asarray(edf_file.readSignal(channel_no['EOGL']))
# EOG-R-A1
data[3,:] = np.asarray(edf_file.readSignal(channel_no['EOGR']))
# chin-EMG
data[4,:] = np.asarray(edf_file.readSignal(channel_no['EMG']))

# Realtime staging requires two epochs (60 seconds) of data. In other words, to score
# the Nth epoch you need both N and N-1 epoch's data. 5 channels of data is required:
# C3-A2 is a numpy vector of 60 seconds from the C3-A2 channel data in micro-volts
# C4-A1 is a numpy vector of 60 seconds from the C4-A1 channel data in micro-volts
# EoGleft-A1 is a numpy vector of 60 seconds from the EoGleft-A1 channel data in micro-volts
# EoGright-A2 is a numpy vector of 60 seconds from the EoGright-A2 channel data in micro-volts
# EMG is a numpy vector of 60 seconds from the EMG channel data in micro-volts
#
# If any channel is missing, simply replace it with a numpy vector of zeros. 

# cannot score the first epoch, so encode it as 9
auto_scores = [9]

# Blank data
blank_data = np.zeros((60*samplig_rate))

#  we will start reading data from N=2 epoch
for i in range(1,total_epochs):
    # get a 60 second window including i-1 and ith epoch
    window = data[:,(i-1)*30*samplig_rate:(i+1)*30*samplig_rate]
    
    # the raw data has to processed first and converted to compressed feature set (CFS) format
    stream = stream_data(C3=window[0,:], C4=window[1,:], EOGL=window[2,:], 
                        EOGR=window[3,:], EMG=window[4,:], sampling_rates=np.ones(5)*samplig_rate)

    # You can score using limited channels for example just EOG channels
    #stream = stream_data(C3=blank_data, C4=blank_data, EOGL=window[2,:], 
    #                    EOGR=window[3,:], EMG=blank_data, sampling_rates=np.ones(5)*samplig_rate)
    
    files = {'file': ('stream.cfs', stream)}

    try:
        print('Scoring epoch number %d.' %(i))
        response = post(server_url + '/realtime', files=files, data={'token':token})
    except:
        print("Error communicating with server")
        stage = [9, 10]

    # If response is successful, it will return the sleep stage and confidence
    # Sleep stage is encoded as 0:Wake, 1 to 3 is NREM 1 to NREM 3, 5 is REM
    # Confidence is a score between 0 and 10. 
    # Low Confidence = 0 to 2
    # Medium Confidence = 2 to 4
    # High confidence = 4 to 10

    if response.status_code != 200:
        print("Error communicating with server")
        stage = [9, 10]
    else:
        response = response.json()
        if response['status'] == 0:
            print("Scoring failed\n")
            print(response['message'])
            stage = [9, 10]
        else:
            stage = response['message']

    auto_scores.append(stage[0])
    sleep_stage = stage_keys[stage[0]]
    confidence = stage[1]

    if stage[1] < 2.0:
        confidence = 'Low'
    elif stage[1] < 4.0:
        confidence = 'Medium'
    else:
        confidence = 'High'

    print('Sleep Stage: %s, Confidence: %s' %(sleep_stage, confidence))



# lets save the automatic scores
print("Saving auto scores in auto_scores.csv")
np.savetxt("auto_scores.csv", auto_scores, delimiter=",", fmt='%s')

# lets convert the scores to numpy array
auto_scores = np.array(auto_scores)

# Lets compare the auto scores with expert scores
with open('expert_scores.csv', 'rt') as f:
    Yb = sum([[int(x) for x in rec] for rec in csv.reader(f, delimiter=',')], [])


# lets convert the scores to numpy array
Yb = np.array(Yb)
auto_scores = np.array(auto_scores)

# replace all unknown scores by wake
Yb[Yb==9] = 0
auto_scores[auto_scores==9] = 0

accuracy = sum(auto_scores==Yb[0:total_epochs])*100.0/total_epochs

kappa = cohen_kappa_score(auto_scores, Yb[0:total_epochs])

print("Auto scoring agreement with expert scorer: %.2f%%, Kappa: %.3f" % (accuracy, kappa))
print("Done.")