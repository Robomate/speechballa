#!/usr/bin/env python
# -*- coding: utf-8 -*-

#https://github.com/igormq/ctc_tensorflow_example

import os
import time
import tensorflow as tf
import scipy.io.wavfile as wav
import numpy as np
from six.moves import xrange as range
try:
    from python_speech_features import mfcc
except ImportError:
    print("Failed to import python_speech_features.\n Try pip install python_speech_features.")
    raise ImportError
from utils import sparse_tuple_from as sparse_tuple_from
from utils import pad_sequences as pad_sequences

# remove warnings from tf
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['CUDA_VISIBLE_DEVICES'] = '0'

def fake_data(num_examples, num_features, num_labels, min_size = 10, max_size=100):

    # Generating different timesteps for each fake data
    np.random.seed(1)
    timesteps = np.random.randint(min_size, max_size, (num_examples,))

    # Generating random input
    np.random.seed(1)
    inputs = np.asarray([np.random.randn(t, num_features).astype(np.float32) for t in timesteps])

    # Generating random label, the size must be less or equal than timestep in order to achieve the end of the lattice in max timestep
    np.random.seed(1)
    labels = np.asarray([np.random.randint(0, num_labels, np.random.randint(1, inputs[i].shape[0], (1,))).astype(np.int64) for i, _ in enumerate(timesteps)])
    
    print('labels.shape')
    #print(labels)
    print(labels[0])
    #print(labels[1])
    print(labels[0].shape)
    print(labels[1].shape)
    print(labels[2].shape)
    print(labels[3].shape)
    print(labels.shape)
    print('inputs.shape')
    #print(inputs[0])
    #print(inputs[1])
    print(inputs[0].shape)
    print(inputs[1].shape)
    print(inputs[2].shape)
    print(inputs[3].shape)
    print(inputs.shape)

    return inputs, labels

# Constants (no meaning in code???!)
SPACE_TOKEN = '<space>'
SPACE_INDEX = 0
FIRST_INDEX = ord('a') - 1  # 0 is reserved to space

# Some configs

# Accounting the 0th indice +  space + blank label = 28 characters
num_classes = ord('z') - ord('a') + 1 + 1 + 1
print('num_classes')
print(num_classes)

# Hyper-parameters
num_epochs = 1       #init: 40 with momentum 0.9
num_hidden = 50       #size hidden layer
num_features = 13     #vector length, coeffs
num_layers = 1
batch_size = 2     #batch size
initial_learning_rate = 1e-2
momentum = 0.9

num_examples = 20       #size for buffer (make bigger than batch_size)
num_batches_per_epoch = int(num_examples/batch_size)

inputs, labels = fake_data(num_examples, num_features, num_classes - 1)

# You can preprocess the input data here
train_inputs = inputs
#~ print('inputs.shape')
#~ print(inputs.shape)

# You can preprocess the target data here
train_targets = labels
#~ print('labels.shape')
#~ print(labels.shape)

# THE MAIN CODE!

graph = tf.Graph()
with graph.as_default():
    # e.g: log filter bank or MFCC features
    # Has size [batch_size, max_stepsize, num_features], but the
    # batch_size and max_stepsize can vary along each step
    inputs = tf.placeholder(tf.float32, [None, None, num_features])

    # Here we use sparse_placeholder that will generate a
    # SparseTensor required by ctc_loss op.
    targets = tf.sparse_placeholder(tf.int32)

    # 1d array of size [batch_size]
    seq_len = tf.placeholder(tf.int32, [None])

    # Defining the cell
    # Can be:
    #   tf.nn.rnn_cell.RNNCell
    #   tf.nn.rnn_cell.GRUCell
    cell = tf.contrib.rnn.LSTMCell(num_hidden, state_is_tuple=True)

    # Stacking rnn cells
    stack = tf.contrib.rnn.MultiRNNCell([cell] * num_layers,
                                        state_is_tuple=True)

    # The second output is the last state and we will no use that
    outputs, _ = tf.nn.dynamic_rnn(stack, inputs, seq_len, dtype=tf.float32)

    shape = tf.shape(inputs)
    batch_s, max_timesteps = shape[0], shape[1]

    # Reshaping to apply the same weights over the timesteps
    outputs = tf.reshape(outputs, [-1, num_hidden])

    # Truncated normal with mean 0 and stdev=0.1
    # Tip: Try another initialization
    # see https://www.tensorflow.org/versions/r0.9/api_docs/python/contrib.layers.html#initializers
    W = tf.Variable(tf.truncated_normal([num_hidden,
                                         num_classes],
                                        stddev=0.1))
    # Zero initialization
    # Tip: Is tf.zeros_initializer the same?
    b = tf.Variable(tf.constant(0., shape=[num_classes]))

    # Doing the affine projection
    logits = tf.matmul(outputs, W) + b

    # Reshaping back to the original shape
    logits = tf.reshape(logits, [batch_s, -1, num_classes])

    # Time major
    logits = tf.transpose(logits, (1, 0, 2))

    loss = tf.nn.ctc_loss(targets, logits, seq_len)
    cost = tf.reduce_mean(loss)

    optimizer = tf.train.MomentumOptimizer(initial_learning_rate,
                                           momentum).minimize(cost)

    
    # Option 1: ctc_greedy_decoder
    #decoded, log_prob = tf.nn.ctc_greedy_decoder(logits, seq_len)
    
    # Option 2: beam_search_decoder (slower but better)
    #decoded, log_prob = tf.nn.ctc_beam_search_decoder(logits, seq_len)
    
    decoded, log_prob = tf.nn.ctc_beam_search_decoder(logits, seq_len,
                        top_paths=3, merge_repeated=True)

    # Inaccuracy: label error rate
    ler = tf.reduce_mean(tf.edit_distance(tf.cast(decoded[0], tf.int32),
                                          targets))

with tf.Session(graph=graph) as session:
    # Initializate the weights and biases
    tf.global_variables_initializer().run()


    for curr_epoch in range(num_epochs):
        train_cost = train_ler = 0
        start = time.time()

        for batch in range(num_batches_per_epoch):

            # Getting the index
            indexes = [i % num_examples for i in range(batch * batch_size, (batch + 1) * batch_size)]
            print('indexes')
            print(indexes)

            batch_train_inputs1 = train_inputs[indexes]
            # Padding input to max_time_step of this batch
            batch_train_inputs, batch_train_seq_len = pad_sequences(batch_train_inputs1)
            
            print('batch_train_inputs')
            #print(batch_train_inputs[0])
            #print('batch_train_inputs[0]')
            #print(batch_train_inputs[1])
            print(batch_train_inputs.shape)
            print('batch_train_seq_len')
            print(batch_train_seq_len)
            print(batch_train_seq_len.shape)
            
            # Converting to sparse representation so as to to feed SparseTensor input
            batch_train_targets = sparse_tuple_from(train_targets[indexes])
            
            print('batch_train_targets.shape')  #is a tuple
            print(len(batch_train_targets))
            print(batch_train_targets[0])
            print(batch_train_targets[0].shape)
            print(batch_train_targets[1])
            print(batch_train_targets[1].shape)
            print(batch_train_targets[2])
            print(batch_train_targets[2].shape)
			

            feed = {inputs: batch_train_inputs,
                    targets: batch_train_targets,
                    seq_len: batch_train_seq_len}

            batch_cost, _ = session.run([cost, optimizer], feed)
            train_cost += batch_cost*batch_size
            train_ler += session.run(ler, feed_dict=feed)*batch_size


        # Shuffle the data
        shuffled_indexes = np.random.permutation(num_examples)
        train_inputs = train_inputs[shuffled_indexes]
        train_targets = train_targets[shuffled_indexes]

        # Metrics mean
        train_cost /= num_examples
        train_ler /= num_examples

        log = "Epoch {}/{}, train_cost = {:.3f}, train_ler = {:.3f}, time = {:.3f}"
        print(log.format(curr_epoch+1, num_epochs, train_cost, train_ler, time.time() - start))

    # Decoding all at once. Note that this isn't the best way

    # Padding input to max_time_step of this batch
    batch_train_inputs, batch_train_seq_len = pad_sequences(train_inputs)

    # Converting to sparse representation so as to to feed SparseTensor input
    batch_train_targets = sparse_tuple_from(train_targets)

    feed = {inputs: batch_train_inputs,
            targets: batch_train_targets,
            seq_len: batch_train_seq_len
            }
            
    #~ print('batch_train_inputs.shape')
    #~ print(batch_train_inputs.shape)
    #~ print('batch_train_targets.shape')
    #~ print(len(batch_train_targets[0]))
    #~ #print(batch_train_targets[0])
    #~ #print(batch_train_targets[1])
    #~ print(batch_train_targets[2])
    #~ print(batch_train_targets[0].shape)
    #~ print(batch_train_targets[1].shape)
    #~ print(batch_train_targets[2].shape)
    #~ print('batch_train_seq_len.shape')
    #~ print(batch_train_seq_len.shape)

    # Decoding
    d = session.run(decoded[0], feed_dict=feed)
    dense_decoded = tf.sparse_tensor_to_dense(d, default_value=-1).eval(session=session)

    for i, seq in enumerate(dense_decoded):

        seq = [s for s in seq if s != -1]

        print('Sequence %d' % i)
        print('\t Original:\n%s' % train_targets[i])
        print('\t Decoded:\n%s' % seq)
