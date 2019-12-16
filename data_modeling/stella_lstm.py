import numpy as np
import pandas as pd

#import lstm
#import time
#import matplotlib.pyplot as plt
#from keras.layers.core import Dense, Activation, Dropout
#from keras.layers.recurrent import LSTM
#from keras.models import Sequential
#import lstm, time #helper libraries



### Functions for preparing LSTM data

def normalize_windows(window_data):
    # this now normalizes every feature
    normalized_data = []
    i=0
    for window in window_data:
        i+=1
        feature_data = []
        for feature in window:
            try:
                normalized_feature_window = [((float(p) / float(feature[0])) - 1) for p in feature]
                feature_data.append(normalized_feature_window)
            except ValueError:
                print(i)
                print(window)
                raise
        normalized_data.append(feature_data)
    return normalized_data

def moving_average(a, n=3) :
    ret = np.cumsum(a, dtype=float)
    ret[n:] = ret[n:] - ret[:-n]
    return ret[n - 1:] / n


def load_data(filename, sequence_length=50, future_shift=20):
    """

    :param filename: name of csv file to read from
    :param sequence_length: length of sequences in input data
    :param future_shift: number of ticks (trades) to shift the future price data
    :return:
    """

    # this is the order the labels were saved in
    # TODO: change the order of the column names to match the files
    df = pd.read_csv(filename, header=None, names=['buyer_order_id',
                                                   'seller_order_id',
                                                   'event_time',
                                                   'ignore',
                                                   'is_buyer_market_maker',
                                                   'quantity',
                                                   'price',
                                                   'symbol',
                                                   'trade_id',
                                                   'event_type',
                                                   'trade_time'])

    # drop useless columns
    df = df.drop(columns=['buyer_order_id','seller_order_id','event_time','ignore','symbol','trade_id','event_type'])
    df['is_buyer_market_maker'] = df['is_buyer_market_maker'].map({' False': -1, ' True': 1})
    # map strings to boolean values

    # define numpy arrays from these series
    np_time = df.trade_time.values
    np_price = df.price.values
    np_ibmm = df['is_buyer_market_maker'].values

    # create sequences
    sequences = []
    for index in range(len(np_price) - sequence_length):
        sequences.append([np_price[index : index+sequence_length],
                          np_time[index : index+sequence_length],
                          np_ibmm[index : index+sequence_length]])

    # shift y values so they represent future prices
    present_prices = np_price[:-(sequence_length+future_shift)]
    y_shifted = np_price[sequence_length+future_shift:]

    # these are the differences between future price and current price
    y_diff = y_shifted - present_prices
    y_diff_smooth = moving_average(y_diff, n=20)

    y_data = y_diff_smooth
    x_data = np.array(normalize_windows(sequences))[:len(y_data)]

    row = round(0.9 * x_data.shape[0])
    x_train = x_data[:int(row),:,:]
    x_test = x_data[int(row):,:,:]

    y_train = y_data[:int(row)]
    y_test = y_data[int(row):]

    return [x_train, y_train, x_test, y_test]

