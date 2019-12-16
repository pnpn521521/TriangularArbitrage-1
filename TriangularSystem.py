from threading import Timer, Thread, Lock
from Events import *
import time
import os
import sys

from binance.client import Client
from ValidPairName import *

from binance.websockets import BinanceSocketManager

import numpy as np

class ThreadPool:
    # acts like a queue for threads to be processed periodically

    def __init__(self, main_thread=None, args=(), debug=False):
        self._system_running = False

        self._periodic_thread = Timer(interval=1, function=self._process_periodic, args=None)
        self._async_thread = Thread(target=self._process_async_pool, args=[])

        if main_thread is None:
            self._main_thread = Thread(target=self._example_main, args=())
        else:
            self._main_thread  = Thread(target=main_thread, args=args)

        self._debug = debug
        self._debug_sync_prev_time = time.time() # DEBUG: for observing any jitter for the synchronous processor
        self._debug_time_lock = Lock()

        self._thread_pool_periodic = queue.Queue(maxsize=0)
        self._periodic_lock = Lock()
        self._thread_pool_async = queue.Queue(maxsize=0)
        self._async_lock = Lock()

    def _process_periodic(self):
        # Tasks synchronized to a one-second period

        if not self._system_running:
            return

        Timer(interval=1, function=self._process_periodic, args=None).start()

        # All threads in pool are passed to the async queue to be processed
        #while self.running:

        # Start all queued processes to the asynchronous queue
        while not self._thread_pool_periodic.empty():
            with self._periodic_lock:
                thread = self._thread_pool_periodic.get()
            with self._async_lock:
                self._thread_pool_async.put(thread)

        # DEBUG: this block prints out a jitter indicator for this function
        if self._debug:
            sync_now = time.time()
            with self._debug_time_lock:
                print('Jitter (ms): ', (sync_now - self._debug_sync_prev_time - 1.0) * 1000)
                self._debug_sync_prev_time = sync_now

        #time.sleep(1)

    def _process_async_pool(self):
        # Process all threads in the asynchronous pool with no delay
        while self._system_running:
            while not self._thread_pool_async.empty():
                with self._async_lock:
                    thread = self._thread_pool_async.get()
                thread.start()

    def _example_main(self):
        # the default main thread if no main thread is passed to this class
        def nothing():
            pass
        # EXAMPLE
        # This function adds threads to the periodic thread pool
        while True:
            for i in range(1000):
                if self._debug and i == 0: # print something so we know the threads are going through
                    with self._periodic_lock:
                        self._thread_pool_periodic.put(Thread(target=print, args='i=0'))
                else:
                    with self._periodic_lock:
                        self._thread_pool_periodic.put(Thread(target=nothing))
            time.sleep(1)

    def start(self):
        self._system_running = True
        self._periodic_thread.start()
        self._async_thread.start()
        self._main_thread.start()

    def terminate(self):
        self._system_running = False

    def put_thread(self, thread):
        # add to the queue to be processed periodically
        with self._periodic_lock:
            self._thread_pool_periodic.put(thread)


class TradingPair:
    # for selling asset_a and buying asset_b

    def __init__(self, asset_a, asset_b, order_type, trade_window=50):
        ### CURRENCY PAIR HANDLES ###
        self.pair = (asset_a, asset_b)
        self.valid_name = valid_pair_name[self.pair]

        ### INVERSION FLAGS ###
        # if inversion is true, sell the base asset of that pair -- else buy the base asset of that pair
        self.inversion = self.valid_name.startswith(asset_a)

        ### ORDER TYPE: 'MARKET' OR 'LIMIT' ###
        self.order_type = order_type

        ### ORDER DIRECTION: 'BUY' OR 'SELL ###
        self.order_direction = 'BUY' if self.inversion else 'SELL'

        ### COEFFICIENT TYPE: 'BEST_BID' OR 'BEST_ASK' ###
        # Determine whether to get the best bid or the best ask for each trade
        if self.order_type == 'LIMIT':
            self.coefficient_type = 'BEST_BID' if (self.order_direction == 'BUY') else 'BEST_ASK'
        else:  # type == 'MARKET'
            self.coefficient_type = 'BEST_ASK' if (self.order_direction == 'BUY') else 'BEST_BID'

        ### DATA STRUCTURES ###
        self.trade_window = trade_window
        self.trades = []
        self.bids = []
        self.asks = []

        ### Transforms ###
        self.np_prices = np.array([])
        self.mean = None
        self.std_dev = None

        self._data_lock = Lock()

    def update_transforms(self):
        self.mean = np.mean(self.np_prices)
        self.std_dev = np.std(self.np_prices)
        return

    def add_trade(self, msg):
        self.trades.append(msg)
        self.trades = self.trades[-self.trade_window:]

        self.np_prices = np.append(self.np_prices, float(msg['p']))[-self.trade_window:]
        self.update_transforms()

        with self._data_lock:
            if msg['m']: # buyer is maker == True
                self.bids.append(msg)
                self.bids = self.bids[-self.trade_window:]
            else:
                self.asks.append(msg)
                self.asks = self.asks[-self.trade_window:]

    def force_get_trade_data(self, client_ptr):
        trades = client_ptr.get_recent_trades(symbol=self.valid_name, limit=self.trade_window)
        for trade in trades:
            # this shortened_trade exists because we need to format these trades to match msg format from web stream
            shortened_trade = {'m': trade['isBuyerMaker'],
                               'p': trade['price'],
                               'T': trade['time'], # TODO: this is either 'T' or 'E', I assumed 'T'
                               'q': trade['qty'],
                               't': trade['id']}
            self.trades.append(shortened_trade)

            self.np_prices = np.append(self.np_prices, float(shortened_trade['p']))[-self.trade_window:]
            self.update_transforms()

            with self._data_lock:
                if shortened_trade['m']: # buyer is maker == True
                    self.bids.append(shortened_trade)
                else:
                    self.asks.append(shortened_trade)



class TriangularArbitrageSystem:

    def __init__(self, asset_a, asset_b, asset_c, order_type_a, order_type_b, order_type_c):

        # SET UP BINANCE API
        self.api_key = os.environ.get('STELLA_API_KEY')
        self.secret_key = os.environ.get('STELLA_SECRET_KEY')
        self.client = Client(self.api_key, self.secret_key)

        # SET UP HANDLES FOR EACH TRADING PAIR
        self.pair_a = valid_pair_name[(asset_a, asset_b)]
        self.pair_b = valid_pair_name[(asset_b, asset_c)]
        self.pair_c = valid_pair_name[(asset_c, asset_a)]
        self.trading_pairs = {self.pair_a: TradingPair(asset_a, asset_b, order_type_a),
                              self.pair_b: TradingPair(asset_b, asset_c, order_type_b),
                              self.pair_c: TradingPair(asset_c, asset_a, order_type_c)}

        ### THREAD SCHEDULING INFRASTRUCTURE ###
        self.thread_pool = ThreadPool(main_thread=self.implicit_profit_thread)

        self._pairs_data_lock = Lock()

        ### SET UP BINANCE TRADE SOCKET ###
        self.trade_socket, self.conn_key_a, self.conn_key_b, self.conn_key_c = self._start_trade_socket()


    def start(self):
        self.thread_pool.start()
        self.trade_socket.start()

    def _start_trade_socket(self):
        trade_socket = BinanceSocketManager(self.client)

        # start any sockets here, i.e. a trade socket
        conn_key_a = trade_socket.start_trade_socket(self.pair_a, lambda msg: self._process_msg_callback(msg, self.pair_a))
        conn_key_b = trade_socket.start_trade_socket(self.pair_b, lambda msg: self._process_msg_callback(msg, self.pair_b))
        conn_key_c = trade_socket.start_trade_socket(self.pair_c, lambda msg: self._process_msg_callback(msg, self.pair_c))

        return trade_socket, conn_key_a, conn_key_b, conn_key_c

    def _process_msg_callback(self, msg, pair_name):
        if msg['e'] == 'error':
            # close and restart the socket
            self.trade_socket.close()
            self.trade_socket, self.conn_key_a, self.conn_key_b, self.conn_key_c = self._start_trade_socket()
            return

        self.add_msg_to_data_structures(msg)

    def add_msg_to_data_structures(self, msg):
        self.trading_pairs[msg['s']].add_trade(msg)
        return

    def add_trade_msg_to_data_structures(self, trade):
        return

    def normalize_prices(self, price_array):
        # logarithmic normalization a la Doing Data Science
        return

    def write_data_for_lstm_thread(self, base_amount=400.0):
        # use this thread to write data into a file for LSTM training
        # the goal is for training data to be as similar to real-time processed data as possible
        return

    def force_get_trade_data(self):
        for pair in self.trading_pairs:
            self.trading_pairs[pair].force_get_trade_data(self.client)
        return

    def implicit_profit_thread(self, base_amount=400.0):
        # calculate an estimate for implicit profit from the market trade stream

        def est_time_to_fill_order(trade_list, now=int(time.time() * 1000)):
            # calculate frequency
            time_delta = now - trade_list[-11]['T']  # in ms TODO: this is either 'T' or 'E', I assumed 'T'
            frequency = (float(len(trade_list[-11:-1])) / time_delta)  # trades / ms
            est_time = 1.0 / frequency
            return est_time

        while True:
            time.sleep(1) # TODO: in a real trading implementation, don't sleep
            try:
                os.system('cls')
                cycle_now = int(time.time() * 1000)

                # TODO: implement an attribute in TradingPair for "best price"
                # TODO: and another attribute for "recent price"

                bids_a, asks_a = self.trading_pairs[self.pair_a].bids, self.trading_pairs[self.pair_a].asks
                with self.trading_pairs[self.pair_a]._data_lock:
                    a_bid_t_est = int(est_time_to_fill_order(bids_a, now=cycle_now)) # to fill bid a
                    a_ask_t_est = int(est_time_to_fill_order(asks_a, now=cycle_now)) # to fill ask a
                    bid_a = bids_a[-1]['p']
                    ask_a = asks_a[-1]['p']
                    mean_a = self.trading_pairs[self.pair_a].mean
                    std_dev_a = self.trading_pairs[self.pair_a].std_dev

                bids_b, asks_b = self.trading_pairs[self.pair_b].bids, self.trading_pairs[self.pair_b].asks
                with self.trading_pairs[self.pair_b]._data_lock:
                    bid_b = bids_b[-1]['p']
                    ask_b = asks_b[-1]['p']
                    mean_b = self.trading_pairs[self.pair_b].mean
                    std_dev_b = self.trading_pairs[self.pair_b].std_dev

                bids_c, asks_c = self.trading_pairs[self.pair_c].bids, self.trading_pairs[self.pair_c].asks
                with self.trading_pairs[self.pair_c]._data_lock:
                    c_ask_t_est =  int(est_time_to_fill_order(asks_c, now=cycle_now)) # to fill ask c
                    c_bid_t_est = int(est_time_to_fill_order(bids_c, now=cycle_now)) # to fill bid c
                    bid_c = bids_c[-1]['p']
                    ask_c = asks_c[-1]['p']
                    mean_c = self.trading_pairs[self.pair_c].mean
                    std_dev_c = self.trading_pairs[self.pair_c].std_dev

                print('bids_a:', [bid['p'] for bid in bids_a][-3:])
                print('asks_a:', [ask['p'] for ask in asks_a][-3:])

                implicit_result = (1.0 / float(bid_a)) * (1.0 / float(ask_b)) * float(ask_c) * base_amount * 0.9985

                implicit_result_other = float(bid_c) * (1.0 / float(bid_b)) * (1.0 / float(ask_a)) * base_amount * 0.9985

                deviation_a = (float(bid_a) - mean_a) / std_dev_a
                deviation_b = (float(ask_b) - mean_b) / std_dev_b
                deviation_c = (float(ask_c) - mean_c) / std_dev_c

                print('implied standard trade profit: $', implicit_result - base_amount)
                print('estimated time to fill bid a: ', a_bid_t_est)
                print('estimated time to fill ask c: ', c_ask_t_est)
                print('estimated time to fill orders total: ', a_bid_t_est + c_ask_t_est)
                print()
                print('implied reverse trade profit:  $', implicit_result_other - base_amount)
                print('estimated time to fill bid c: ', c_bid_t_est)
                print('estimated time to fill ask a: ', a_ask_t_est)
                print('estimated time to fill orders total: ', c_bid_t_est + a_ask_t_est)
                print()
                print('order a deviation: ', deviation_a)
                print('order b deviation: ', deviation_b)
                print('order c deviation: ', deviation_c)

                #self.force_get_trade_data() # TODO: remove this and use a socket callback instead

            except IndexError:
                self.force_get_trade_data()


tas = TriangularArbitrageSystem('USDT', 'BNB', 'BCC', 'LIMIT', 'MARKET', 'LIMIT')
tas.start()
