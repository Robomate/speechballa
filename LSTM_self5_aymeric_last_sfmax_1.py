#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''=======================================================================
#Purpose: Acoustic Model (Speech Recognition)
#
#Model:   LSTM
#         e.g. 500 nodes each layer, trained with Adam
#
#Inputs:  Bavarian Speech Corpus (German)
#		  training utterances: 		56127
#		  validation utterances: 	 7012
#         test utterances: 		 	 7023
#         --------------------------------
#		  total					    70162
#
#		  shape of input: 39 MFCCcoeff vector
#
#Output:  135 classes (45 monophones with 3 HMM states each)
#Version: 4/2017 Roboball (MattK.)
#Start tensorboard via bash: 	tensorboard --logdir /logfile/directory
#Open Browser for tensorboard:  localhost:6006
#tensorboard --logdir /home/praktiku/korf/speechdata/tboard_logs/MLP_5layer_2017-05-10_14:04
#======================================================================='''

import numpy as np
import tensorflow as tf
import tensorflow.contrib.layers as layers
from tensorflow.contrib import rnn
import random
import re
import datetime 
import matplotlib.pyplot as plt
import matplotlib.image as pltim
import os
import scipy.io
import h5py
import pandas
map_fn = tf.map_fn

try:
	import cPickle as pickle
except:
   import _pickle as pickle

# remove warnings from tf
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'

########################################################################
# define functions:
########################################################################

def load_name_files(filenames):
	'''load dataset-names from .txt files:'''
	#load dataset-names from .txt files:
	return np.genfromtxt(filenames, delimiter=" ",dtype='str')

def load_pat_data(filename, headerbytes):
	'''load Pattern files:x num of coefficients, 12byte header'''
	with open(filename, 'rb') as fid:
		frames = np.fromfile(fid, dtype=np.int32) #get frames
		#print (frames[0])
		fid.seek(headerbytes, os.SEEK_SET)  # read in without header offset
		datafile = np.fromfile(fid, dtype=np.float32).reshape((frames[0], coeffs)).T 
	return datafile

def create_random_vec(randomint, epochlength):
	'''create random vector'''
	np.random.seed(randomint)
	randomvec = np.arange(epochlength)
	np.random.shuffle(randomvec)
	return randomvec
	
def random_shuffle_data(randomint, dataset_name):
	'''based on createRandomvec shuffle data randomly'''
	datasetlength = len(dataset_name)
	#init random list
	dataset_rand = []
	#create random vector
	randomvec = create_random_vec(randomint, datasetlength)
	#fill random list
	for pos in range(datasetlength):
		dataset_rand.append(dataset_name[randomvec[pos]])
	return dataset_rand

def pad_zeros(data_file, label_file):
	'''pad data and labels with zeros or cut data to layer length'''
	data_len = data_file.shape[1]
	label_len = label_file.shape[0]
	assert data_len == label_len, "Error: Data and Label length differ."	
	if	data_len < nodes:
		# zero pad data
		pad_len = nodes - data_len
		data_zeros = np.zeros([coeffs,pad_len])
		data_padded = np.concatenate((data_file, data_zeros), axis=1)
		# zero pad labels
		label_zeros = 100 * np.ones([pad_len])
		label_padded = np.concatenate((label_file, label_zeros), axis=0)
	elif data_len > nodes:
		# cut data, labels to layer length
		data_padded = data_file[:,0:nodes]
		label_padded = label_file[0:nodes]	
	else:
		# process data, labels unchanged
		data_padded = data_file
		label_padded = label_file
	return data_padded.T, label_padded

def create_minibatch(minibatchsize,nodes,coeffs,filenames):
	'''create Minibatch for data and labels'''
	minibatch_data = np.zeros([minibatchsize,nodes,coeffs])
	minibatch_label = np.zeros([minibatchsize,nodes,classnum])
	for batch in range(minibatchsize):
		# load data
		data_file = load_pat_data(datapath + filenames[batch], headerbytes)
		# load labels
		label_txt = filenames[batch][:-4]+".txt"
		label_input = labelpath + label_txt
		label_file = np.loadtxt(label_input)
		# zero padding
		data_padded, label_padded = pad_zeros(data_file, label_file)
		minibatch_data[batch,:,:] = data_padded
		#labels: one-hot-encoding
		for pos_lab in range(nodes):
			label = int(label_padded[pos_lab])
			minibatch_label[batch][pos_lab][label-1] = 1.0					
	return minibatch_data, minibatch_label
		

########################################################################
# init parameter
########################################################################

print('=============================================')
print("load filenames")
print('=============================================\n')

# fix initial randomness:
randomint = 1
modtype = "RNN" 
modlayer = 1	 	

# get timestamp:
timestamp = str(datetime.datetime.now())
daytime = timestamp[11:-10]
date = timestamp[0:-16]
timemarker = date+"_" + daytime

# init paths:
#path 	 = 'C:/Users/MCU.angelika-HP/Desktop/Korf2017_05/Bachelorarbeit/BA_05/' #on win
#path 	 = "/home/praktiku/korf/BA_05/" #on praktiku@dell9
path 	 = "/home/korf/Desktop/BA_05/" #on korf@lynx5 (labor)
pathname = "00_data/dataset_filenames/"
logdir = "tboard_logs/"
data_dir = "00_data/pattern_hghnr_39coef/"
label_dir = "00_data/nn_output/"	 
tboard_path = path + logdir
tboard_name = modtype + "_"+ str(modlayer)+ "layer_"+ str(timemarker)

# init filenames:
trainset_filename = 'trainingset.txt'
validationset_filename = 'validationset.txt'
testset_filename = 'testset.txt'

#load filenames:
trainset_name = load_name_files(path + pathname + trainset_filename)
valset_name = load_name_files(path + pathname + validationset_filename)
testset_name = load_name_files(path + pathname + testset_filename)
			
# init model parameter:
coeffs = 39  
nodes = 500					#time_steps
classnum = 135 							#number of output classes
framenum = 1 							#number of frames
inputnum = framenum * coeffs 				#length of input vector
display_step = 100 						#to show progress
bnorm = 'no_bnorm'
lnorm = 'no_lnorm'
	
# init training parameter:
epochs = 1	                            #1 epoch: ca. 1hour10min
learnrate = 1e-4                        #high:1e-4
train_size  = len(trainset_name) 
val_size = len(valset_name)
tolerance = 0.01                        #break condition  
batsize_train = 256													
train_samples = int(train_size/batsize_train)
#train_samples = 10

# init test parameter:
test_size = len(testset_name)	
batsize_test = 100
batches_test = int(test_size / batsize_test)   #round down
buffer_test = 10
test_samples = int(test_size/buffer_test)    #number of test_samples
test_samples = 10


# init emission probs parameter	
batsize_test2=1
buffer_test2=1
test_samples2=10

#random shuffle filenames:
valset_rand = random_shuffle_data(randomint, valset_name)
#print(valset_rand)

#init params:		 
headerbytes = 12
datapath  = path + data_dir 
labelpath = path + label_dir

# init activation function:
actdict = ["tanh", "relu", "sigmoid"]
acttype = actdict[0]

USE_LSTM = False
hidden_dim   = 100         #size of hidden states
time_steps = nodes

########################################################################
# init and define model:
########################################################################

# init model:
def weight_variable(shape):
	'''init weights'''
	initial = tf.truncated_normal(shape, stddev=0.1)
	return tf.Variable(initial, name="W")
	
def bias_variable(shape):
	'''init biases'''
	initial = tf.constant(0.1, shape=shape)
	return tf.Variable(initial, name="b")

def dense(x, W, b, name="dense"):
	'''matrix vector multiplication'''
	with tf.name_scope(name):
		return tf.add(tf.matmul(x, W), b)

# init placeholder:
x_input  = tf.placeholder(tf.float32, (None, time_steps, coeffs))  # (batch,time in)
y_target = tf.placeholder(tf.float32, (None, classnum)) # for last softmax only!! (batch,classes)
#y_target = tf.placeholder(tf.float32, (None,time_steps, classnum)) # for all softmaxs (batch,time_steps,classes)

# init weights:	
# 1. hidden layer
with tf.name_scope(name="W_dense"):
	W_out = weight_variable([hidden_dim, classnum]) 
	b_out = bias_variable([classnum])
	tf.summary.histogram("weights", W_out)
	tf.summary.histogram("biases", b_out)

########################################################################
# define lstm cell:
########################################################################

if USE_LSTM:
    cell = tf.nn.rnn_cell.BasicLSTMCell(hidden_dim, state_is_tuple=True)
else:
    cell = tf.nn.rnn_cell.BasicRNNCell(hidden_dim)

with tf.variable_scope("Rnn"):
	output, states = tf.nn.dynamic_rnn(cell, x_input, dtype=tf.float32)

# use  forlast softmax only!!

#last out needs shape[batch, classnum] (256,135)
last_out = dense(output[:,-1,:], W_out, b_out, name="last_dense")

# define loss, optimizer, accuracy:
with tf.name_scope("cross_entropy"):
	cross_entropy = tf.reduce_mean(
	tf.nn.softmax_cross_entropy_with_logits(logits= last_out,labels = y_target))
	tf.summary.scalar("cross_entropy", cross_entropy)

with tf.name_scope("train"):
	optimizer = tf.train.AdamOptimizer(learnrate).minimize(cross_entropy)
	
with tf.name_scope("accuracy"):
	correct_prediction = tf.equal(tf.argmax(last_out,1), tf.argmax(y_target,1))
	accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
	tf.summary.scalar("accuracy", accuracy)

# merge all summaries for tensorboard:	
summ = tf.summary.merge_all()

# init tf session :
sess = tf.InteractiveSession()
# save and restore all the variables:
saver = tf.train.Saver()
# start session:
sess.run(tf.global_variables_initializer()) 
# init tensorboard
writer = tf.summary.FileWriter(tboard_path + tboard_name)
writer.add_graph(sess.graph)

# print out model info:
print("**********************************")
print("model:"+str(1)+" hidden layer"+str(modtype))
print("**********************************")
print("hidden units: "+str(nodes)+" each layer")
print("activation function: "+str(acttype))
print("optimizer: Adam")
print("----------------------------------")
print("data name: RVG new German speech corpus")
print("training data: " +str(train_size))
print("validation data: " +str(val_size))
print("test data: " +str(test_size)+"\n")

########################################################################
# training loop:
########################################################################

def training(epochs,train_samples):
	'''train the neural model'''
	print('=============================================')
	print('start '+str(modtype)+' training')
	print('=============================================')
	t1_1 = datetime.datetime.now()
	
	# init cost, accuracy:
	crossval_history = np.empty(shape=[0],dtype=float)
	cost_history = np.empty(shape=[0],dtype=float)
	train_acc_history = np.empty(shape=[0],dtype=float)

	# epoch loop:
	for epoch in range(1,epochs+1):
		
		#random shuffle filenames for each epoch:
		randomint_train = epoch
		trainset_rand = random_shuffle_data(randomint_train, trainset_name)
		
		#training loop: length = int(train_size/buffersamples)	
		for minibatch in range(train_samples):
			#grab linear utterances (buffersamples) from random trainset:
			trainset_buffer = trainset_rand[minibatch * batsize_train:(minibatch * batsize_train) + batsize_train]
		
			# minibatch_data [Batch Size, Sequence Length, Input Dimension]
			#(None, 200, 39)
			minibatch_data, minibatch_label = create_minibatch(batsize_train,nodes,coeffs,trainset_buffer)
			#print(minibatch_data[0,:,:])	
			#print(minibatch_data.shape)	
			
			#check for last softmax only!!:
			minibatch_label_last = minibatch_label[:,-1,:]
			#print(minibatch_label_last.shape)
			
			#start feeding data into the model:
			feedtrain = {x_input: minibatch_data, y_target: minibatch_label_last}
			optimizer.run(feed_dict = feedtrain)
			
			#log history for tensorboard
			if minibatch % 5 == 0:
				[train_accuracy, s] = sess.run([accuracy, summ], feed_dict=feedtrain)
				writer.add_summary(s, minibatch)
				
			#get cost_history, accuracy history data:
			cost_history = np.append(cost_history,sess.run(cross_entropy,feed_dict=feedtrain))
			train_acc_history = np.append(train_acc_history,sess.run(accuracy,feed_dict=feedtrain))
			
			#check progress: training accuracy
			if  minibatch%10 == 0:
				train_accuracy = accuracy.eval(feed_dict=feedtrain)
				crossvalidationloss = sess.run(cross_entropy,feed_dict=feedtrain)
				crossval_history = np.append(crossval_history,crossvalidationloss)
				t1_2 = datetime.datetime.now()
				print('epoch: '+ str(epoch)+'/'+str(epochs)+
				' -- training utterance: '+ str(minibatch * batsize_train)+'/'+str(train_size)+
				" -- cross validation loss: " + str(crossvalidationloss)[0:-2])
				print('training accuracy: %.2f'% train_accuracy + 
				" -- training time: " + str(t1_2-t1_1)[0:-7])
				
			#~ #stopping condition:
			#~ #if abs(crossval_history[-1] - crossval_history[-2]) < tolerance:
				#~ #break
		print('=============================================')
	
	print('=============================================')
	#Total Training Stats:
	total_trainacc = np.mean(train_acc_history, axis=0)
	print("overall training accuracy %.3f"%total_trainacc)       
	t1_3 = datetime.datetime.now()
	train_time = t1_3-t1_1
	print("total training time: " + str(train_time)[0:-7]+'\n')	
	
	return train_acc_history, cost_history, crossval_history, train_time, total_trainacc	
			
			
		
		
		
		
		
		
		
		
		
			
training(epochs,train_samples)



