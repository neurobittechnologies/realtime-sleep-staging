#!/usr/bin/python
# Reference code for real-time sleep staging and intervention
# Please refer to the basic demo before you refer to this code
# Prerequisites: Basic knowledge of Python, REST API, parallel 
# processing/multi-threading, pipes and multi-process communication
# 
# Call to both the real-time module and the plotting is done asynchrnously 
# So the main loop can run very fast
#
# tested on Python 3.6 on Windows platform
# requires these python libraries:
# pycfslib, pyedflib, pygame, pebble, pyqtgraph, 
# pillow, PyQt5, requests, numpy and scipy
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

import os
import csv
import warnings
import numpy as np
from requests import post
from plotter import PlotData
from time import time, sleep
import multiprocessing as mp
from pebble import ProcessPool
from dataserver import DataServer
from pycfslib import create_stream_v2 as stream_data

# hide the pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

# Ignore any warnings - You may want to remove this line
warnings.filterwarnings("ignore")

# Load the audio used for TMR here
pygame.mixer.init()
sound = pygame.mixer.Sound('tmr.wav')


# Login information for Z3Score
# Note that real-time module is only available on V2 of the API
# Always use https instead of http to ensure security
server_url = 'https://z3score.com/api/v2'
# Do not have a key? Request one from contact@neurobit.io
# Make sure you request access to the real-time module.
email = 'demo@neurobit.io'
key = 'YourAccessKey'

# Score once every 3 seconds, 3 to 10 seconds is recommended.
SCORING_FREQUENCY = 3 

# Buffer size (B) in ms, this is the buffer size for the fake data server
# readouts from the server must be made within B ms, otherwise a buffer overflow happens
# and some data is lost. Unless, you need extremely precise feedback, buffer size could be large
# For closed loop phase targeted feedback use 50ms, 20 ms is achievable on fast machines or if you remove the
# GUI plotting of real-time data. when phase targeting is not necessary you can increase it to 500ms or more
BUFFER_SIZE = 100

# Update the real-time plot every 20 ms
# plotting is a CPU intensive task, if Buffer size is very small,
# we recommend you disable plotting entirely or increase the plot update time
PLOT_UPDATE_TIME = 50

# No of seconds to wait between Audio Plays
REFRACTORY_PERIOD = 5


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
def request_token():
    # Check license validity
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
    return token


# Function to stage sleep data 
# Staging requires two epochs (60 seconds) of data. In other words, to score
# the Nth epoch you need both N and N-1 epoch's data. 5 channels of data is required:
# C3-A2 is a numpy vector of 60 seconds from the C3-A2 channel data in micro-volts
# C4-A1 is a numpy vector of 60 seconds from the C4-A1 channel data in micro-volts
# EoGleft-A1 is a numpy vector of 60 seconds from the EoGleft-A1 channel data in micro-volts
# EoGright-A2 is a numpy vector of 60 seconds from the EoGright-A2 channel data in micro-volts
# EMG is a numpy vector of 60 seconds from the EMG channel data in micro-volts
#
# If any channel is missing, simply replace it with a numpy vector of zeros. 
# sampling_rates is a list of size 5 with sampling rates of C3, C4, EOGL, EOGR and EMG respectively
# token is the authorization token

def process_and_stage(C3, C4, EOGL, EOGR, EMG, sampling_rates, token):
    # the raw data must be processed and converted to compressed feature set (CFS) 
    # data stream before it can be scored. Realtime module requires the V2 of the CFS library
    # which is create_stream_v2 function. It takes five channels and their sampling rates
    stream = stream_data(C3, C4, EOGL, EOGR, EMG, sampling_rates)
    files = {'file': ('stream.cfs', stream)}

    try:
        response = post(server_url + '/realtime', files=files, data={'token':token})
    except:
        print("Error communicating with server")
        return [9, 10]

    if response.status_code != 200:
        print("Error communicating with server")
        stage = [9, 10]
    else:
        data = response.json()
        if data['status'] == 0:
            print("Scoring failed\n")
            print(data['message'])
            stage = [9, 10]
        else:
            stage = data['message']

    return stage


# The main function begins
if __name__=="__main__":
    # request an authorization token 
    token = request_token()
    
    # DataServer is a fake data server that reads data from an offline
    # EDF file instead of a real EEG device. This is for demonstration
    # purpose only. Buffer size is the time within which you must read data
    # otherwise a buffer overflow occurs. Your EEG device manufacturer will
    # have their own libraries to read real-time data. Please adapt this code
    # accordingly
 
    server = DataServer(buffer_size=BUFFER_SIZE)
    # Sampling rate of the data
    sampling_rate = server.sampling_rate
    # total samples read
    samples_read = 0

    # running_window is exactly 60 seonds long
    # the real-time module operates on 60 seconds (two epochs) of data 
    # to score the latest 30 seconds (one epoch) 
    length = 60*sampling_rate
    running_window = np.zeros((5,length))
    blank_data = np.zeros((length))
    sleep_stages = []

    # Plot realtime data for last 30 seconds or 1 epoch
    # We use the multiprocessing library to make asynchrnous 
    # calls to the real time plotting function through a pipe. 
    # Plotting so much data in real-time is a CPU intensive process
    # So use of parallel processing library is necessary when Buffer size is small
    # and very fast feedback is required.
    plot_pipe, plotter_pipe = mp.Pipe()
    send = plot_pipe.send

    # The PlotData class, plots the data in realtime
    # We use pyqtgraph is an order of magnitude faster than matplotlib
    plotter = PlotData(data = running_window[:,30*sampling_rate:], 
            channel_names=channel_names, scoring_speed=SCORING_FREQUENCY, acquisition_latency=BUFFER_SIZE)

    # send data to the plotter through a pipe
    plot_process = mp.Process(
            target=plotter, args=(plotter_pipe,), daemon=True)

    # start the plot_process
    plot_process.start()
    sleep(1.0)

    # Staging will also be done asynchronously
    # We use the library pebble instead of multiprocessing 
    # as it allows you to cancel a process 
    # more details here: https://pythonhosted.org/Pebble/
    executor = ProcessPool(max_workers=2)

    # This will store the server response 
    responses = []
    stage = [9, 10]
    last_call_success = False
    plot_update_time = time()
    last_played = time()

    # data aquisition loop
    # this loop must run fast enough that all operations are completed before
    # the buffer fills up
    while True:

        buffer = server.read_buffer()

        # No more data available
        if buffer is None:
            break

        samples = buffer.shape[1]
        samples_read += samples
        t_now = samples_read/sampling_rate
        
        # push new data into running_window and remove old data
        running_window[:,0:length-samples] = running_window[:,samples:]
        running_window[:,length-samples:] = buffer

        # Wait for buffer to fill up 
        # We need exactly 60 seconds of data before we can stage
        if samples_read < length:
            # update the plot every PLOT_UPDATE_TIME ms
            if time() - plot_update_time > PLOT_UPDATE_TIME/1000:
                command ={} 
                command['data'] = running_window[:,30*sampling_rate:]
                command['stage'] = None
                command['confidence'] = 10
                command['latency'] = 0
                command['t_now'] = t_now
                send(command)
                plot_update_time = time()

            continue

        # This is the first call to the server
        if not responses:
            latency = 0
            last_staging_request_time = time()
            t_stage = t_now
            # You can use limited channels to do the scoring as well
            # for channels which are missing use blank_data which is simply
            # a vector of 0s of 60 second duration 
            responses.append(executor.schedule(process_and_stage, (running_window[0,:], running_window[1,:], running_window[2,:], 
                        running_window[3,:], running_window[4,:], np.ones(5)*sampling_rate, token), timeout=SCORING_FREQUENCY))

        if responses[-1].done() and not last_call_success:
            stage = responses[-1].result()
            #sleep_stages.append(np.hstack((t_stage, stage)))
            sleep_stages.append([t_stage, stage_keys[stage[0]], stage[1]])
            print("Time: %0.2f Stage: %s Confidence: %0.2f" %(t_stage, stage_keys[stage[0]], stage[1]))
            latency = (time() - last_staging_request_time)*1000
            last_call_success = True

        if time() - last_staging_request_time > SCORING_FREQUENCY:
            # last request did not complete in time!
            if not responses[-1].done():
                # Cancel the request
                responses[-1].cancel()
                print("Warning: scoring could not be completed in stipulated time.")
                print("Try reducing the SCORING_FREQUENCY.")
                latency = (time() - last_staging_request_time)*1000
                stage = [9, 10]
                sleep_stages.append([t_stage, stage_keys[stage[0]], stage[1]])
                print("Time: %0.2f Stage: %s Confidence: %0.2f" %(t_stage, stage_keys[stage[0]], stage[1]))
            
            # Now make a new request
            last_staging_request_time = time()
            t_stage = t_now
            
            # You can use limited channels to do the scoring as well
            # for channels which are missing use blank_data which is simply
            # a vector of 0s of 60 second duration 
            responses.append(executor.schedule(process_and_stage, (running_window[0,:], running_window[1,:], running_window[2,:], 
                        running_window[3,:], running_window[4,:], np.ones(5)*sampling_rate, token), timeout=SCORING_FREQUENCY))
            
            last_call_success = False

        # TMR play audio if conditions are fulfilled 
        # If SWS with confidence > 4 
        if stage[0] == 3 and stage[1] > 4 and time() - last_played > REFRACTORY_PERIOD:
            print('Playing audio cue')
            # pygame play is an asyncronous function 
            sound.play()
            last_played = time()

        # Plot the data 
        # update the plot every PLOT_UPDATE_TIME ms
        if time() - plot_update_time > PLOT_UPDATE_TIME/1000:
            command ={} 
            command['data'] = running_window[:,30*sampling_rate:]
            command['stage'] = stage_keys[stage[0]]
            command['confidence'] = stage[1]
            command['latency'] = latency
            command['t_now'] = t_now
            send(command)
            plot_update_time = time()
  
    
    print('Stream ended...')
    print('Saving sleep score is realtime_score.csv')
    with open('realtime_score.csv', 'w') as myfile:
        wr = csv.writer(myfile, delimiter=',', quoting=csv.QUOTE_MINIMAL, lineterminator = '\n')
        wr.writerow(['Time (sec)', 'Stage ', 'Confidence '])
        for stages in sleep_stages:
            wr.writerow(stages)
        
    # Stop the plotter
    send(None)