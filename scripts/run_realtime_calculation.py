import time
import requests

import os
import sys
import inspect

current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0,parent_dir)

from binance.client import Client

# this is the primary script for forward testing and data collection
# test implicit profit based on live prices
# TODO: implement live price forecasting with neural network

client = Client(os.environ.get('STELLA_API_KEY'), os.environ.get('STELLA_SECRET_KEY'))

def get_bids_and_asks(n=200, symbol='ETHUSDT'):
    # get the last n trades and sort them into bids and asks
    trades = client.get_recent_trades(symbol=symbol, limit=n)
    bids = []
    asks = []
    for trade in trades:
        if trade['isBuyerMaker'] == True:
            bids.append(trade)
        else:
            asks.append(trade)
    return bids, asks

def est_time_to_fill_order(trade_list, now=int(time.time()*1000)):
    # calculate frequency
    time_delta = now - trade_list[-11]['time'] # in ms
    #print(time_delta)
    frequency = (float(len(trade_list[-11:-1])) / time_delta) # trades / ms
    #print(frequency)
    est_time = 1.0 / frequency
    #print(est_time) # in ms
    return est_time

def async_update(out_file='trade_results.csv'):
    # run this periodically

    #debug_time = time.time()
    #print('debug_time: ', debug_time)
    cycle_now = int(time.time()*1000)

    # TODO: subtract trading fees
    bids_a, asks_a = get_bids_and_asks(n=200, symbol='BNBUSDT') # invert
    bids_b, asks_b = get_bids_and_asks(n=200, symbol='BCCBNB') # invert
    bids_c, asks_c = get_bids_and_asks(n=200, symbol='BCCUSDT') # don't invert

    # format the data for a standard direction trade
    implicit_result = 1.0/float(bids_a[-1]['price']) * 1.0/float(asks_b[-1]['price']) * float(asks_c[-1]['price']) * 500.0
    a_bid_t_est = int(est_time_to_fill_order(bids_a, now=cycle_now))
    c_ask_t_est =  int(est_time_to_fill_order(asks_c, now=cycle_now))
    a_bid_qty = float(bids_a[-1]['qty'])
    c_ask_qty = float(asks_c[-1]['qty'])
    print('implied standard trade profit: $', implicit_result - 500.0)
    print('estimated time to fill order a: ', a_bid_t_est)
    print('estimated time to fill order c: ', c_ask_t_est)
    print('estimated time to fill orders total: ', a_bid_t_est + c_ask_t_est)

    # format the data for a reverse direction trade
    implicit_result_other = float(bids_c[-1]['price']) * 1.0/float(bids_b[-1]['price']) * 1.0/float(asks_a[-1]['price']) * 500.0
    c_bid_t_est = int(est_time_to_fill_order(bids_c, now=cycle_now))
    a_ask_t_est = int(est_time_to_fill_order(asks_a, now=cycle_now))
    c_bid_qty = float(bids_c[-1]['qty'])
    a_ask_qty = float(asks_a[-1]['qty'])
    print('implied reverse trade profit:  $', implicit_result_other - 500.0)
    print('estimated time to fill order c: ', c_bid_t_est)
    print('estimated time to fill order a: ', a_ask_t_est)
    print('estimated time to fill orders total: ', c_bid_t_est + a_ask_t_est)
    print()

    # this can be written to a csv file
    out_string = ', '.join([str(int(time.time())),
                            str(implicit_result - 500.0),
                            str(a_bid_t_est),
                            str(c_ask_t_est),
                            str(a_bid_t_est + c_ask_t_est),
                            str(a_bid_qty),
                            str(c_ask_qty),
                            str(implicit_result_other - 500.0),
                            str(c_bid_t_est),
                            str(a_ask_t_est),
                            str(c_bid_t_est + a_ask_t_est),
                            str(c_bid_qty),
                            str(a_ask_qty),])

    print()


while True:
    try:
        async_update(out_file='test_data.csv')
        time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        print('KeyboardInterrupt or SystemExit')
        raise
    except IndexError:
        # TODO: handle exception where we don't have enough bids/asks
        print('IndexError occurred... Sleeping for 2 seconds')
        time.sleep(2)
    except requests.exceptions.ConnectionError:
        print('Connection timeout error... Sleeping for 10 seconds.')
        time.sleep(10)
    except:
        print(sys.exc_info())
        print('Exception occurred... Exiting.')
        exit(1)
