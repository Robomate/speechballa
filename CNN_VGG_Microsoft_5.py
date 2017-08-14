#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
#=======================================================================
#Purpose: Acoustic Model (Speech Recognition) 
#
#Model:   2 Hidden Layer CNN
#         trained with Adam
#
#Inputs:  RVG new (German)
#		  training utterances: 		56127
#		  validation utterances: 	 7012
#         test utterances: 		 	 7023
#         --------------------------------
#		  total					    70162						
#
#		  shape of input: 39MFCCcoeff * x frames
#
#Output:  mono: 135 classes (45 monophones with 3 HMM states each)
#		  tri: 4643 classes (tied triphones states out of 40014)
#
#Version: 6/2017 Roboball (MattK.)

#Start tensorboard via bash: 	tensorboard --logdir /logfile/directory
#Open Browser for tensorboard:  localhost:6006
#tensorboard --logdir /home/praktiku/korf/speechdata/tboard_logs/MLP_5layer_2017-05-10_14:04
#=======================================================================
'''

import numpy as np
import tensorflow as tf
import random
import re
import datetime 
import matplotlib.pyplot as plt
import matplotlib.image as pltim
import os
import scipy.io
import pandas as pd

try:
	import cPickle as pickle
except:
   import _pickle as pickle

# remove warnings from tf
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['CUDA_VISIBLE_DEVICES'] = '0'

########################################################################
# define functions:
########################################################################

def loadNamefiles(filenames):
	'''load dataset-names from .txt files:'''
	return np.genfromtxt(filenames, delimiter=" ",dtype='str')
		
def loadPatData(filename, headerbytes):
	'''load Pattern files:x num of coefficients, 12byte header'''
	with open(filename, 'rb') as fid:
		frames = np.fromfile(fid, dtype=np.int32) #get frames
		fid.seek(headerbytes, os.SEEK_SET)  # read in without header offset
		datafile = np.fromfile(fid, dtype=np.float32).reshape((frames[0], coeffs)).T 
	return datafile

def padUtterance(framenum, labelfile, datafile):
	'''pad utterance on both sides'''
	if labelfile.shape[0] != datafile.shape[1]:
		labelfile = labelfile[0:-1]	
	# extract start and end vectors
	startveclabel = int(labelfile[0])
	startvecdata = datafile[:,0]
	endveclabel = int(labelfile[-1])
	endvecdata = datafile[:,-1]	
	# compose pads
	startmatlabel = np.tile(startveclabel,int((framenum-1)/2))
	startmatdata = np.tile(startvecdata,(int((framenum-1)/2),1)).T	
	endmatlabel = np.tile(endveclabel,int((framenum-1)/2))
	endmatdata = np.tile(endvecdata,(int((framenum-1)/2),1)).T	
	# pad utterance
	paddedlabel = np.concatenate((startmatlabel, labelfile, endmatlabel), axis=0)
	paddeddata = np.concatenate((startmatdata,datafile, endmatdata), axis=1)		
	return paddedlabel, paddeddata
	
def slidingWin(framenum, paddedlabel, paddeddata,randomint):
	'''create sliding windows to extract chunks'''
	# init: empty lists
	labellist=[]
	datalist=[]	
	if randomint != -11:
		# randomize frame order for training
		rnd_pos = createRandomvec(randomint, paddedlabel.shape[0]-framenum+1)
	# sliding window over utterance
	for pos in range(paddedlabel.shape[0]-framenum+1):
		if randomint != -11:
			pos = rnd_pos[pos]
		slicedata = paddeddata[:,pos:pos+framenum]
		slicelabel = paddedlabel[pos:pos+framenum]
		label = slicelabel[int((framenum-1)/2)]
		labellist.append(label)
		datalist.append(slicedata)	
	return labellist, datalist
	
def createRandomvec(randomint, epochlength):
	'''create random vector'''
	np.random.seed(randomint)
	randomvec = np.arange(epochlength)
	np.random.shuffle(randomvec)
	return randomvec

def randomShuffleData(randomint, dataset_name):
	'''based on createRandomvec shuffle data randomly'''
	datasetlength = len(dataset_name)
	# init random list
	dataset_rand = []
	# create random vector
	randomvec = createRandomvec(randomint, datasetlength)
	# fill random list
	for pos in range(datasetlength):
		dataset_rand.append(dataset_name[randomvec[pos]])
	return dataset_rand
		
def createMinibatchData(minibatchsize, framenum, databuffer):
	'''create minibatches from databuffer'''
	minibatchdata = np.zeros(shape=(minibatchsize,coeffs,framenum))	
	# save matrices to minibatch array
	for pos in range(minibatchsize):
		minibatchdata[pos][:][:] = databuffer[pos]
	minibatch_data = minibatchdata[:,:,:,np.newaxis]
	return minibatch_data

def createMinibatchLabel(minibatchsize , classnum, labelbuffer):
	'''create one hot encoding from labels'''
	# init labels with zeros
	minibatchlabel = np.zeros(shape=(minibatchsize,classnum))	
	# one-hot-encoding
	for labelpos in range(minibatchsize):	
		label = int(labelbuffer[labelpos])
		minibatchlabel[labelpos][label-1] = 1.0
	return minibatchlabel	

def Preprocess(framenum, randbatnum, dataset_name, path,randomint):
	'''load data and label files, pad utterance, create chunks'''
	# init params:		 
	headerbytes = 12
	datapath  = path + data_dir
	labelpath = path + label_dir	
	# load data file:
	datafilename = datapath + dataset_name[randbatnum]
	datafile = loadPatData(datafilename, headerbytes)	
	# load label file:
	dataset_namelab = dataset_name[randbatnum][:-4]+".txt"
	inputlabel = labelpath + dataset_namelab
	labelfile = np.loadtxt(inputlabel) #read in as float
	# pad utterance:
	paddedlabel, paddeddata = padUtterance(framenum, labelfile, datafile)
	# extract vector and labels by sliding window:
	labellist, datalist = slidingWin(framenum, paddedlabel, paddeddata,randomint)
	return labellist, datalist

def Databuffer(buffersamples, framenum, dataset_name, path,randomint):
	'''create buffer for minibatch'''
	# init buffer
	label_buffer = []
	data_buffer = []	
	for pos in range(buffersamples):		
		labellist, datalist = Preprocess(framenum, pos, dataset_name, path,randomint)
		label_buffer = label_buffer + labellist
		data_buffer = data_buffer + datalist
	return label_buffer, data_buffer

def rand_buffer(label_buffer, data_buffer):
	'''randomize buffer order for minibatch'''
	SEED = 10
	random.seed(SEED)
	random.shuffle(label_buffer)
	random.seed(SEED)
	random.shuffle(data_buffer)
	return label_buffer, data_buffer

def phonemeDict():
	'''Dictionary for classes'''
	phoneme_dict = ["@","a","a:","aI","an","ar","aU","b","C","d","e:","E",
	"E:","f","g","h","i:","I","j","k","l","m","n","N","o:","O","Oe","On",
	"OY","p","r","s","S","sil","sp","t","u","u:","U","v","x","y:","Y","z","Z"]
	#create label translation
	phoneme_lab = np.arange(classnum).astype('str')
	pos=0
	for phoneme in phoneme_dict:
		phoneme_lab[pos*3:pos*3+3] = phoneme
		pos += 1
	return phoneme_lab
	
def phonemeTranslator(labels,phoneme_labels):
	'''translate labels into phonemes'''
	label_transcript = np.copy(labels).astype(str)	
	for pos in range(len(labels)):
		phon = phoneme_labels[int(labels[pos])-1]
		label_transcript[pos] = phon	
	#print("labels utterance: "+str(labels))
	#print(label_transcript)	
	return label_transcript

########################################################################
# init parameter
########################################################################

print('=============================================')
print("load filenames")
print('=============================================\n')

# fix initial randomness:
randomint = 1
modtype = "CNN_VGG" 
modlayer = 14	 	

# get timestamp:
timestamp = str(datetime.datetime.now())
daytime = timestamp[11:-10]
date = timestamp[0:-16]
timemarker = date+"_" + daytime

# init paths:
path 	 = "/home/korf/Desktop/BA_05/" #on korf@alien2 ,korf@lynx5(labor)
#path 	 = "/home/praktiku/korf/BA_05/" #on praktiku@dell9
#path 	 = "/home/praktiku/Videos/BA_05/" #on praktiku@dell8 (labor)
pathname = "00_data/dataset_filenames/"

#RVG corpus:------------------------------------------------------------
data_dir = "00_data/RVG/pattern_hghnr_39coef/"
#data_dir = "00_data/RVG/pattern_dft_16k/"
#data_dir = "00_data/RVG/pattern_dft_16k_norm/"

label_dir = "00_data/RVG/nn_output/"
#label_dir = "00_data/RVG/nn_output_tri/"

#ERI corpus:------------------------------------------------------------
data_dir_eri = "00_data/ERI/pattern_hghnr_39coef/"
label_dir_eri = "00_data/ERI/nn_output_mono/"

#~ data_dir = "00_data/ERI/pattern_hghnr_39coef/"
#~ label_dir = "00_data/ERI/nn_output_mono/"

logdir = "tboard_logs/"
tboard_path = path + logdir
tboard_name = modtype + "_"+ str(modlayer)+ "layer_"+ str(timemarker)

# init filenames:
trainset_filename = 'trainingset.txt'
validationset_filename = 'validationset.txt'
testset_filename = 'testset.txt'

#load filenames:
trainset_name = loadNamefiles(path + pathname + trainset_filename)
valset_name = loadNamefiles(path + pathname + validationset_filename)
testset_name = loadNamefiles(path + pathname + testset_filename)
			
# init model parameter:
coeffs = 39                             # MFCC: 39, DFT:257
classnum = 135 							#classes mono: 135, tri:4643
framenum = 13						#number of frames
inputnum = framenum * coeffs 				#length of input vector
display_step = 100 						#to show progress
bnorm = 'no_bnorm'
lnorm = 'no_lnorm'
optimizing = 'adam'
classifier = 'softmax'

# error message frame number:
if framenum%2==0:
	print("Error, please choose uneven number of frames.")

#calculate params for dense layer
re_coeff = ((framenum + 1)/2)
if re_coeff%2 == 0:
	re_coeff = re_coeff/2
else:
	re_coeff = (re_coeff + 1)/2
re_coeff = int(re_coeff)	
	
# init activation function:
actdict = ["tanh", "relu", "selu","sigmoid"]
acttype = actdict[1]

# init training parameter:
epochs = 10                           #1 epoch: ca. 1hour10min
learnrate = 1e-4                        #high:1e-4
train_size  = len(trainset_name) 
val_size = len(valset_name)
tolerance = 0.01                        #break condition  
batsize_train = 64 * 4													
batches_train = int(train_size / batsize_train) #round down
buffer_train = 10 		#choose number utterances in buffer
train_samples = int(train_size/buffer_train)

# init test parameter:
test_size = len(testset_name)	
batsize_test = 100
batches_test = int(test_size / batsize_test)   #round down
buffer_test = 10
test_samples = int(test_size/buffer_test)    #number of test_samples

# init emission probs parameter	
batsize_test2=1
buffer_test2=1
test_samples2=10

#random shuffle filenames:
valset_rand = randomShuffleData(randomint, valset_name)
#random shuffle weights inits:
rand_w = createRandomvec(randomint, modlayer+1)

# unit testing
#~ epochs = 1
#~ train_samples = 10
#~ test_samples = 10

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

def matmul(x, W, b, name="fc"):
	'''matrix vector multiplication'''
	with tf.name_scope(name):
	  return tf.add(tf.matmul(x, W), b)
		
def dense(x, W, b, name="dense"):
	'''matrix vector multiplication'''
	with tf.name_scope(name):
		return tf.add(tf.matmul(x, W), b)

def selu(x):
	'''Selu activation function'''
	with ops.name_scope('elu') as scope:
		alpha = 1.6732632423543772848170429916717
		scale = 1.0507009873554804934193349852946
		return scale*tf.where(x>=0.0, x, alpha*tf.nn.elu(x))
		 
def activfunction(x, acttype):
	'''activation functions'''
	if acttype == "tanh":
		activation_array = tf.tanh(x)
	elif acttype == "relu":
		activation_array = tf.nn.relu(x)
	elif acttype == "selu":
		activation_array = selu(x)	
	else:
		activation_array = tf.sigmoid(x)
	return activation_array

def conv2d(x, W):
	'''convolution operation (cross correlation)'''
	return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='SAME')

def max_pool_2x2(x):
	'''max pooling'''
	return tf.nn.max_pool(x, ksize=[1, 2, 2, 1],
                        strides=[1, 2, 2, 1], padding='SAME')
                        
# set conv hyperparams:
f1 = 3
f1_d = 1 * 96
f3_fc = 4 * 1024

# init weights:                   
W_conv1 = weight_variable([f1, f1, 1, f1_d])
b_conv1 = bias_variable([f1_d])
W_conv2 = weight_variable([f1, f1, f1_d, f1_d])
b_conv2 = bias_variable([f1_d])
W_conv3 = weight_variable([f1, f1, f1_d,f1_d])
b_conv3 = bias_variable([f1_d])

W_conv4 = weight_variable([f1, f1,f1_d, 2*f1_d])
b_conv4 = bias_variable([2*f1_d])
W_conv5 = weight_variable([f1, f1,2*f1_d,2*f1_d])
b_conv5 = bias_variable([2*f1_d])
W_conv6 = weight_variable([f1, f1,2*f1_d, 2*f1_d])
b_conv6 = bias_variable([2*f1_d])
W_conv7 = weight_variable([f1, f1, 2*f1_d, 2*f1_d])
b_conv7 = bias_variable([2*f1_d])

W_conv8 = weight_variable([f1, f1, 2*f1_d,4*f1_d])
b_conv8 = bias_variable([4*f1_d])
W_conv9 = weight_variable([f1, f1,4*f1_d, 4*f1_d])
b_conv9 = bias_variable([4*f1_d])
W_conv10 = weight_variable([f1, f1,4*f1_d,4*f1_d])
b_conv10 = bias_variable([4*f1_d])
W_conv11 = weight_variable([f1, f1,4*f1_d, 4*f1_d])
b_conv11 = bias_variable([4*f1_d])

W_fc1 = weight_variable([re_coeff * 10 * 4 * f1_d, f3_fc])
b_fc1 = bias_variable([f3_fc])
W_fc2 = weight_variable([f3_fc, f3_fc])
b_fc2 = bias_variable([f3_fc])
W_fc3 = weight_variable([f3_fc, classnum])
b_fc3 = bias_variable([classnum])

# init placeholder:
x_input = tf.placeholder(tf.float32, shape=[None, coeffs, framenum, 1],name="input")
y_target = tf.placeholder(tf.float32, shape=[None, classnum],name="labels")

# 1.conv block   
h_conv1 = tf.nn.relu(conv2d(x_input , W_conv1) + b_conv1)
h_conv2 = tf.nn.relu(conv2d(h_conv1, W_conv2) + b_conv2)
h_conv3 = tf.nn.relu(conv2d(h_conv2, W_conv3) + b_conv3)
h_pool1 = max_pool_2x2(h_conv3)	
# 2.conv block
h_conv4 = tf.nn.relu(conv2d(h_conv3 , W_conv4) + b_conv4)
h_conv5 = tf.nn.relu(conv2d(h_conv4, W_conv5) + b_conv5)
h_conv6 = tf.nn.relu(conv2d(h_conv5, W_conv6) + b_conv6)
h_conv7 = tf.nn.relu(conv2d(h_conv6 , W_conv7) + b_conv7)
h_pool2 = max_pool_2x2(h_conv7)
# 3.conv block
h_conv8 = tf.nn.relu(conv2d(h_pool2, W_conv8) + b_conv8)
h_conv9 = tf.nn.relu(conv2d(h_conv8 , W_conv9) + b_conv9)
h_conv10 = tf.nn.relu(conv2d(h_conv9, W_conv10) + b_conv10)
h_conv11 = tf.nn.relu(conv2d(h_conv10 , W_conv11) + b_conv11)
h_pool3 = max_pool_2x2(h_conv11)
# dense Layer
h_flat = tf.reshape(h_pool3, [-1, re_coeff * 10 * 4 * f1_d])
h_fc1 = tf.nn.relu(tf.matmul(h_flat, W_fc1) + b_fc1)
h_fc2 = tf.nn.relu(tf.matmul(h_fc1, W_fc2) + b_fc2)
# readout Layer
dense_out = tf.matmul(h_fc2, W_fc3) + b_fc3

# define classifier, cost function:
softmax = tf.nn.softmax(dense_out)

# define loss, optimizer, accuracy:
with tf.name_scope("cross_entropy"):
	cross_entropy = tf.reduce_mean(
	tf.nn.softmax_cross_entropy_with_logits(logits= dense_out,labels = y_target))
	tf.summary.scalar("cross_entropy", cross_entropy)
with tf.name_scope("train"):
	optimizer = tf.train.AdamOptimizer(learnrate).minimize(cross_entropy)
with tf.name_scope("accuracy"):
	correct_prediction = tf.equal(tf.argmax(dense_out,1), tf.argmax(y_target,1))
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
print("model: "+str(modlayer)+ " hidden layer "+str(modtype))
print("**********************************")
print("input frames: "+str(framenum))
print("activation function: "+str(acttype))
print("optimizer: Adam")
print("----------------------------------")
print("data name: RVG new")
print("training data: " +str(train_size))
print("validation data: " +str(val_size))
print("test data: " +str(test_size)+"\n")

########################################################################
# training loop:
########################################################################

def training(epochs=1,train_samples=10):
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
		
		# random shuffle training-set for each epoch:
		randomint_train = epoch
		trainset_rand = randomShuffleData(randomint_train, trainset_name)
		# random shuffle validation-set:
		randomint_val = 1
		valset_rand = randomShuffleData(randomint_val, valset_name)
		
		# training loop: length = int(train_size/buffersamples)	
		for buffernum in range(train_samples):
			
			# grab linear utterances (buffersamples) from random trainset:
			trainset_buffernum = trainset_rand[buffernum * buffer_train:(buffernum * buffer_train) + buffer_train]	
			# create buffer:
			label_buffer, data_buffer = Databuffer(buffer_train, framenum, trainset_buffernum, path,randomint_train)
			# randomize buffer order for minibatch
			label_buffer, data_buffer = rand_buffer(label_buffer, data_buffer)
			# get number of minibatches from buffer:
			bufferlength = len(label_buffer)
			minibatches = int(bufferlength/batsize_train)
			
			# minibatch loop per buffer:
			for batch in range(minibatches):
				# grab linear minibatch datavectors from databuffer:
				datavector = data_buffer[batch * batsize_train: (batch * batsize_train)+batsize_train]		
				# grab linear minibatch labels from labelbuffer:		
				labelvector = label_buffer[batch * batsize_train: (batch * batsize_train)+batsize_train]		
				# minibatch data:
				trainbatchdata = createMinibatchData(batsize_train, framenum, datavector)
				# minibatch labels: one hot encoding
				trainbatchlabel = createMinibatchLabel(batsize_train, classnum, labelvector)
						
				# start feeding data into the model:
				feedtrain = {x_input: trainbatchdata, y_target: trainbatchlabel}
				optimizer.run(feed_dict = feedtrain)
					
				# log history for tensorboard
				if batch % 5 == 0:
					[train_accuracy, s] = sess.run([accuracy, summ], feed_dict=feedtrain)
					writer.add_summary(s, batch)
					
				# get cost_history, accuracy history data:
				cost_history = np.append(cost_history,sess.run(cross_entropy,feed_dict=feedtrain))
				train_acc_history = np.append(train_acc_history,sess.run(accuracy,feed_dict=feedtrain))
			
			# check progress: training accuracy
			if  buffernum%10 == 0:
				# grab linear utterances (buffersamples) from random trainset:
				valset_buffernum = trainset_rand[buffernum * buffer_train:(buffernum * buffer_train) + buffer_train]	
				# create buffer:
				rng_val = -11
				label_buffer_val, data_buffer_val = Databuffer(buffer_train, framenum, trainset_buffernum, path,rng_val)
				# get number of minibatches from buffer:
				bufferlength_val = len(label_buffer_val)
				minibatches_val = int(bufferlength_val/batsize_train)
				# minibatch loop per buffer:
				for batch_val in range(minibatches_val):
					# grab linear minibatch datavectors from databuffer:
					datavector_val = data_buffer_val[batch_val * batsize_train: (batch_val * batsize_train)+batsize_train]		
					# grab linear minibatch labels from labelbuffer:		
					labelvector_val = label_buffer_val[batch_val * batsize_train: (batch_val * batsize_train)+batsize_train]		
					# minibatch data:
					valbatchdata = createMinibatchData(batsize_train, framenum, datavector_val)
					# minibatch labels: one hot encoding
					valbatchlabel = createMinibatchLabel(batsize_train, classnum, labelvector_val)
							
				# start feeding data into the model:
				feedval = {x_input: valbatchdata, y_target: valbatchlabel}
				train_accuracy = accuracy.eval(feed_dict=feedval)
				crossvalidationloss = sess.run(cross_entropy,feed_dict=feedval)
				crossval_history = np.append(crossval_history,crossvalidationloss)
				
				t1_2 = datetime.datetime.now()
				print('epoch: '+ str(epoch)+'/'+str(epochs)+
				' -- training utterance: '+ str(buffernum * buffer_train)+'/'+str(train_size)+
				" -- cross validation loss: " + str(crossvalidationloss)[0:-2])
				print('training accuracy: %.2f'% train_accuracy + 
				" -- training time: " + str(t1_2-t1_1)[0:-7])
				
			#~ #stopping condition:
			#~ if abs(crossval_history[-1] - crossval_history[-2]) < tolerance:
				#~ break
		print('=============================================')
	
	print('=============================================')
	# Total Training Stats:
	total_trainacc = np.mean(train_acc_history, axis=0)
	print("overall training accuracy %.3f"%total_trainacc)       
	t1_3 = datetime.datetime.now()
	train_time = t1_3-t1_1
	print("total training time: " + str(train_time)[0:-7]+'\n')	
	
	return train_acc_history, cost_history, crossval_history, train_time, total_trainacc
	
	
########################################################################
#start testing:
########################################################################

def testing(test_samples=10,batsize_test=1,buffer_test=10, randomint_test=1):
	'''test the neural model'''
	print('=============================================')
	print('start '+str(modtype)+' testing')
	print('=============================================')
	t2_1 = datetime.datetime.now()
	
	# init histories
	test_acc_history = np.empty(shape=[0],dtype=float)
	test_filenames_history = np.empty(shape=[0],dtype=str)
	test_softmax_list = []
	label_transcript_list = []
	test_max_transcript_list = []
	random_int = -11
	
	# get label-dictionary:
	phoneme_labels = phonemeDict()
	if test_samples < 20:
		print("phoneme_labels: ")
		print(phoneme_labels)
		print(" ")
	
	# random shuffle filenames:	
	testset_rand = randomShuffleData(randomint_test, testset_name)
	
	# test loop: length = int(test_size/buffersamples)
	for buffernum in range(int(test_samples)):
			
			# grab linear minibatch datavectors from databuffer:
			testset_buffernum = testset_rand[buffernum * buffer_test: (buffernum * buffer_test)+buffer_test]
			test_filenames_history = np.append(test_filenames_history,testset_buffernum)
			
			# create buffer:
			labelbuffer, datavectorbuffer = Databuffer(buffer_test, framenum, testset_buffernum, path, random_int)	
			bufferlength = len(labelbuffer)
			
			# get label to phoneme transcription:
			label_transcript = phonemeTranslator(labelbuffer, phoneme_labels)
			
			# get number of minibatches from buffer:
			minibatches = int(bufferlength/batsize_test)
			#~ print("number of minibatches: "+str(minibatches))
			
			# init histories
			test_softmax_utterance = np.empty(shape=[0,classnum],dtype=float)
			
			# minibatch loop per buffer:
			for batch in range(minibatches):
				
				# grab minibatch datavectors from databuffer:
				datavector = datavectorbuffer[batch * batsize_test: (batch * batsize_test)+batsize_test]		
				# grab minibatch labels from labelbuffer:		
				labelvector = labelbuffer[batch * batsize_test: (batch * batsize_test)+batsize_test]
							
				# minibatch data:
				testbatchdata = createMinibatchData(batsize_test, framenum, datavector)
				# minibatch labels: one hot encoding
				testbatchlabel = createMinibatchLabel(batsize_test, classnum, labelvector)
				
				# start feeding data into the model:
				feedtest = {x_input: testbatchdata, y_target: testbatchlabel}
				predictions = accuracy.eval(feed_dict = feedtest)
				test_acc_history = np.append(test_acc_history,predictions)
				
				if test_samples < 20:
					# get emissionprobs
					softmaxprobs = sess.run(softmax,feed_dict=feedtest)
					test_softmax_utterance = np.append(test_softmax_utterance,softmaxprobs, axis=0)
			
			if test_samples < 20:
				# save emission-probs for each utterance
				test_softmax_list.append(test_softmax_utterance)
				
				# translation to phonemes
				testmax_loc = test_softmax_utterance.argmax(axis=1)
				test_max_transcript = np.zeros_like(testmax_loc).astype(str)
				for loc in range(len(testmax_loc)):
					test_max_transcript[loc] = phoneme_labels[testmax_loc[loc]]
				test_max_transcript_list.append(test_max_transcript)
				label_transcript_list.append(label_transcript)
				print('=============================================')
				print("test utterance: " + str(buffernum+1))
				print("label name: " + testset_buffernum[0]+"\n")
				print("label_transcript: ")
				print(str(label_transcript))
				print('test_max_transcript: ')
				print(str(test_max_transcript)+"\n")
		
			# check progress: test accuracy
			if  buffernum%10 == 0:
				test_accuracy = accuracy.eval(feed_dict=feedtest)			
				t2_2 = datetime.datetime.now()
				print('test utterance: '+ str(buffernum*buffer_test)+'/'+str(test_size))
				print('test accuracy: %.2f'% test_accuracy + 
				" -- test time: " + str(t2_2-t2_1)[0:-7])
					
	print('=============================================')
	# total test stats:
	print('test utterance: '+ str(test_size)+'/'+str(test_size))
	total_testacc = np.mean(test_acc_history, axis=0)
	print("overall test accuracy %.3f"%total_testacc)       
	t2_3 = datetime.datetime.now()
	test_time = t2_3-t2_1
	print("total test time: " + str(test_time)[0:-7]+'\n')		
	
	# info to start tensorboard:
	print('=============================================')
	print("tensorboard")
	print('=============================================')
	print("to start tensorboard via bash enter:")
	print("tensorboard --logdir " + tboard_path + tboard_name)
	print("open your Browser with:\nlocalhost:6006")
	
	testparams_list = [test_acc_history, test_filenames_history, 
					   test_softmax_list, randomint_test]
	
	return testparams_list, total_testacc, test_time, phoneme_labels

########################################################################
#start main: 
########################################################################

# start training: 
train_acc_history, cost_history, crossval_history, train_time, total_trainacc = training(epochs,train_samples)
# start testing: full set
testparams_list, total_testacc, test_time, phoneme_labels  = testing(test_samples,batsize_test,buffer_test)
# start testing: emission probs
testparams_list2, total_testacc2, test_time2, phoneme_labels = testing(test_samples2,batsize_test2,buffer_test2)


########################################################################
#plot settings:
########################################################################

# plot model summary:
plot_model_sum = "model_summary: "+str(modtype)+"_"+str(modlayer)+" hid_layer, "+\
                          " ,"+" frames: "+\
                          str(framenum)+", classes: " +str(classnum)+", epochs: "+str(epochs)+"\n"+\
                          bnorm+ ", "+ lnorm+", "+"training accuracy %.3f"%total_trainacc+\
                          " , test accuracy %.3f"%total_testacc+" , "+\
                          str(timemarker)
                          
# define storage path for model:
model_path = path + "03_SpeechCNN/pretrained_CNN/"
model_name = str(timemarker)+"_"+modtype + "_"+ str(modlayer)+ "lay_"+ str(framenum)+ "fs_"+\
             str(coeffs)+ "coeffs_"+\
             str(classnum)+ "class_" +str(epochs)+"eps_"+\
             acttype+"_"+ bnorm+ "_"+ lnorm+\
             "_"+str(total_testacc)[0:-9]+"testacc"
print("Model saved to: ")
print(model_path + model_name)
                  
# init moving average:
wintrain = 300
wintest = 300
wtrain_len = len(cost_history)
if wtrain_len < 100000:
	wintrain = 5
wtest_len = len(testparams_list[0])
if wtest_len < 10000:
	wintest = 5
	
#=======================================================================
#plot training
#=======================================================================

# plot training loss function
fig1 = plt.figure(1, figsize=(8,8))
plt.figtext(.5,.95,plot_model_sum, fontsize=10, ha='center')
plt.subplots_adjust(wspace=0.5,hspace=0.5)
plt.subplot(211)
plt.plot(range(len(cost_history)),cost_history, color='#1E90FF')
plt.plot(np.convolve(cost_history, np.ones((wintrain,))/wintrain, mode='valid'), color='#97FFFF', alpha=1)
plt.axis([0,len(cost_history),0,int(10)+1])
# plt.axis([0,len(cost_history),0,int(np.max(cost_history))+1])
plt.title('Cross Entropy Training Loss')
plt.xlabel('number of batches, batch size: '+ str(batsize_train))
plt.ylabel('loss')

# plot training accuracy function
plt.subplot(212)
plt.plot(range(len(train_acc_history)),train_acc_history, color='#20B2AA')
plt.plot(np.convolve(train_acc_history, np.ones((wintrain,))/wintrain, mode='valid'), color='#7CFF95', alpha=1)
plt.axis([0,len(cost_history),0,1])
plt.title('Training Accuracy')
plt.xlabel('number of batches, batch size:'+ str(batsize_train))
plt.ylabel('accuracy percentage')

# export figure
plt.savefig('imagetemp/'+model_name+"_fig1"+'.jpeg', bbox_inches='tight')
im1 = pltim.imread('imagetemp/'+model_name+"_fig1"+'.jpeg')
#pltim.imsave("imagetemp/out.png", im1)

#=======================================================================
#plot testing
#=======================================================================

# plot validation loss function
plt.figure(2, figsize=(8,8))
plt.figtext(.5,.95,plot_model_sum, fontsize=10, ha='center')
plt.subplots_adjust(wspace=0.5,hspace=0.5)
plt.subplot(211)
plt.plot(range(len(crossval_history)),crossval_history, color='#1E90FF')
plt.plot(np.convolve(crossval_history, np.ones((wintrain,))/wintrain, mode='valid'), color='#87CEFA', alpha=1)
plt.axis([0,len(crossval_history),0,int(10)+1])
#plt.axis([0,len(crossval_history),0,int(np.max(crossval_history))+1])
plt.title('Cross Validation Loss')
plt.xlabel('number of validation checks')
plt.ylabel('loss')

#plot test accuracy function
plt.subplot(212)
plt.plot(range(len(testparams_list[0])),testparams_list[0], color='m')
plt.plot(np.convolve(testparams_list[0], np.ones((wintest,))/wintest, mode='valid'), color='#F0D5E2', alpha=1)
plt.axis([0,len(testparams_list[0]),0,1])
plt.title('Test Accuracy')
plt.xlabel('number of batches, batch size: '+ str(batsize_test))
plt.ylabel('accuracy percentage')

# export figure
plt.savefig('imagetemp/'+model_name+"_fig2"+'.jpeg', bbox_inches='tight')
im2 = pltim.imread('imagetemp/'+model_name+"_fig2"+'.jpeg')

########################################################################
#start export:
########################################################################

print('=============================================')
print("start export")
print('=============================================')

print("Model saved to: ")
print(model_path + model_name)

#.mat file method:------------------------------------------------------

#create dict model
model = {"model_name" : model_name}
#modelweights
model["W_conv1"] = np.array(sess.run(W_conv1))
model["b_conv1"] = np.array(sess.run(b_conv1))
model["W_conv2"] = np.array(sess.run(W_conv2))
model["b_conv2"] = np.array(sess.run(b_conv2))
model["W_conv3"] = np.array(sess.run(W_conv3))
model["b_conv3"] = np.array(sess.run(b_conv3))

model["W_conv4"] = np.array(sess.run(W_conv4))
model["b_conv4"] = np.array(sess.run(b_conv4))
model["W_conv5"] = np.array(sess.run(W_conv5))
model["b_conv5"] = np.array(sess.run(b_conv5))
model["W_conv6"] = np.array(sess.run(W_conv6))
model["b_conv6"] = np.array(sess.run(b_conv6))
model["W_conv7"] = np.array(sess.run(W_conv7))
model["b_conv7"] = np.array(sess.run(b_conv7))

model["W_conv8"] = np.array(sess.run(W_conv8))
model["b_conv8"] = np.array(sess.run(b_conv8))
model["W_conv9"] = np.array(sess.run(W_conv9))
model["b_conv9"] = np.array(sess.run(b_conv9))
model["W_conv10"] = np.array(sess.run(W_conv10))
model["b_conv10"] = np.array(sess.run(b_conv10))
model["W_conv11"] = np.array(sess.run(W_conv11))
model["b_conv11"] = np.array(sess.run(b_conv11))

model["W_fc1"] = np.array(sess.run(W_fc1))
model["b_fc1"] = np.array(sess.run(b_fc1))
model["W_fc2"] = np.array(sess.run(W_fc2))
model["b_fc2"] = np.array(sess.run(b_fc2))
model["W_fc3"] = np.array(sess.run(W_fc3))
model["b_fc3"] = np.array(sess.run(b_fc3))
model["acttype1"] = acttype
#modellayout
model["hiddenlayer"] = modlayer
model["classnum"] = classnum
model["framenum"] = framenum
model["randomint"] = randomint
model["classification"] = classifier 
model["optimizer"] = optimizing
#trainingparams
model["epochs"] = epochs
model["learnrate"] = learnrate
model["batsize_train"] = batsize_train
model["total_trainacc"] = total_trainacc
#testparams
model["batsize_test"] = batsize_test
model["randomint_test"] = testparams_list[3]
model["total_testacc"] = total_testacc
#history = [cost_history, train_acc_history, test_acc_history]
model["cost_history"] = cost_history
model["train_acc_history"] = train_acc_history
model["test_acc_history"] = testparams_list[0]

#from testing: files and emission probs
model["test_filenames_history"] = testparams_list2[1]
model["test_softmax_list"] = testparams_list2[2]
model["batch_norm"] = bnorm
model["layer_norm"] = lnorm
model["phoneme_labels"] = phoneme_labels
#modelw["label_transcript_list"] = label_transcript_list
#modelw["test_max_transcript_list"] = test_max_transcript_list

#save plot figures
model["fig_trainplot"] = im1
model["fig_testplot"] = im2

#export to .csv file
model_csv = [timemarker,total_trainacc,total_testacc,
             modtype,modlayer,framenum, coeffs, 'No',classnum,
             classifier,epochs,acttype,learnrate,optimizing,
             bnorm,lnorm,batsize_train,batsize_test, 'No',
             f1,f1_d,f3_fc]
df = pd.DataFrame(columns=model_csv)


#save only good models
if total_trainacc > 0.25:
	scipy.io.savemat(model_path + model_name,model)
	df.to_csv('nn_model_statistics/nn_model_statistics.csv', mode='a')
	df.to_csv('nn_model_statistics/nn_model_statistics_backup.csv', mode='a')
	
print('=============================================')
print("export finished")
print('=============================================')
print(" "+"\n")

#print out model summary:
print('=============================================')
print("model summary")
print('=============================================')
print("*******************************************")
print("model: "+ str(modtype)+"_"+ str(modlayer)+" hidden layer")
print("*******************************************")
print("frame inputs: "+str(framenum))
print("activation function: "+str(acttype))
print("optimizer: Adam")
print("-------------------------------------------")
print("data name: RVG new")
print("training data: " +str(train_size))
print("validation data: " +str(val_size))
print("test data: " +str(test_size))
print("-------------------------------------------")
print(str(modtype)+' training:')
print("total training time: " + str(train_time)[0:-7])
print("overall training accuracy %.3f"%total_trainacc ) 
print("-------------------------------------------")
print(str(modtype)+' testing:')
print("total test time: " + str(test_time)[0:-7])	
print("overall test accuracy %.3f"%total_testacc) 
print("*******************************************")


#plot show options:----------------------------------------------------------
#plt.show()
#plt.hold(False)
#plt.close()



