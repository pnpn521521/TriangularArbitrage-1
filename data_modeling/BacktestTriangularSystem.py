from binance.client import Client
from ValidPairName import *
from static_exchange_info import *

from binance.websockets import BinanceSocketManager

import warnings

with warnings.catch_warnings():
    # Hide messy warnings
    warnings.simplefilter('ignore')

    import os, sys, inspect

    current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)

    import time

    import numpy as np
    import math

    import pandas as pd

    import pickle

    import matplotlib.pyplot as plt

    from decimal import *


def generate_df():
    df_a = pd.read_csv('../data/BNBUSDT_backtest_3.csv', header=0, index_col='trade_time',
                     names= ['a_event_time', # E
                             'a_ignore', # M
                             'trade_time', # T
                             'a_seller_order_id', # a
                             'a_buyer_order_id', # b
                             'a_event_type', # e
                             'a_is_buyer_maker', # m
                             'a_price', # p
                             'a_quantity', # q
                             'a_symbol', # s
                             'a_trade_id' # t
                            ])
    # drop useless columns
    df_a = df_a.drop(columns=['a_buyer_order_id','a_seller_order_id','a_event_time','a_ignore','a_symbol','a_event_type'])

    # get rid of the stupid = signs I accidentally put in the data
    df_a = df_a.applymap(lambda x: x.split('=')[-1])

    df_a.index = df_a.index.map(lambda x: x.split('=')[-1])

    # format data
    df_a.index = pd.to_datetime(df_a.index, unit='ms')
    df_a['a_price'] = df_a['a_price'].values
    df_a['a_quantity'] = df_a['a_quantity'].values
    df_a['a_trade_id'] = df_a['a_trade_id'].values
    # map strings to boolean values
    df_a['a_is_buyer_maker'] = df_a['a_is_buyer_maker'].map({'False': -1, 'True': 1})

    #df_a = df_a.drop_duplicates(keep='last')

    df_a = df_a.resample('s').last().fillna(value=None,method='ffill')



    df_b = pd.read_csv('../data/BCCBNB_backtest_3.csv', header=0, index_col='trade_time',
                     names= ['b_event_time', # E
                             'b_ignore', # M
                             'trade_time', # T
                             'b_seller_order_id', # a
                             'b_buyer_order_id', # b
                             'b_event_type', # e
                             'b_is_buyer_maker', # m
                             'b_price', # p
                             'b_quantity', # q
                             'b_symbol', # s
                             'b_trade_id' # t
                            ])
    # drop useless columns
    df_b = df_b.drop(columns=['b_buyer_order_id','b_seller_order_id','b_event_time','b_ignore','b_symbol','b_event_type'])

    # get rid of the stupid = signs I accidentally put in the data
    df_b = df_b.applymap(lambda x: x.split('=')[-1])

    df_b.index = df_b.index.map(lambda x: x.split('=')[-1])

    # format data
    df_b.index = pd.to_datetime(df_b.index, unit='ms')
    df_b['b_price'] = df_b['b_price'].values
    df_b['b_quantity'] = df_b['b_quantity'].values
    df_b['b_trade_id'] = df_b['b_trade_id'].values

    # map strings to boolean values
    df_b['b_is_buyer_maker'] = df_b['b_is_buyer_maker'].map({'False': -1, 'True': 1})

    #df_b = df_b.drop_duplicates(keep='last')

    df_b = df_b.resample('s').last().fillna(value=None,method='ffill')



    df_c = pd.read_csv('../data/BCCUSDT_backtest_3.csv', header=0, index_col='trade_time',
                     names= ['c_event_time', # E
                             'c_ignore', # M
                             'trade_time', # T
                             'c_seller_order_id', # a
                             'c_buyer_order_id', # b
                             'c_event_type', # e
                             'c_is_buyer_maker', # m
                             'c_price', # p
                             'c_quantity', # q
                             'c_symbol', # s
                             'c_trade_id' # t
                            ])
    # drop useless columns
    df_c = df_c.drop(columns=['c_buyer_order_id','c_seller_order_id','c_event_time','c_ignore','c_symbol','c_event_type'])

    # get rid of the stupid = signs I accidentally put in the data
    df_c = df_c.applymap(lambda x: x.split('=')[-1])

    df_c.index = df_c.index.map(lambda x: x.split('=')[-1])

    # format data
    df_c.index = pd.to_datetime(df_c.index, unit='ms')
    df_c['c_price'] = df_c['c_price'].values
    df_c['c_quantity'] = df_c['c_quantity'].values
    df_c['c_trade_id'] = df_c['c_trade_id'].values

    # map strings to boolean values
    df_c['c_is_buyer_maker'] = df_c['c_is_buyer_maker'].map({'False': -1, 'True': 1})

    #df_c = df_c.drop_duplicates(keep='last')

    df_c = df_c.resample('s').last().fillna(value=None,method='ffill')

    df = df_a.join(df_c,how='outer')
    df = df.join(df_b,how='outer')

    df = df.dropna()

    with open('backtest_df.p', 'wb') as out_file:
        pickle.dump(df, out_file)

    return df

class TradingPair:
    # for selling asset_a and buying asset_b

    def __init__(self, asset_a, asset_b, order_type, letter, trade_window=50):
        # asset_a is what we start with and we want to exchange it for asset_b
        # we want to sell asset_a and buy asset_b

        ### CURRENCY PAIR HANDLES ###
        self.pair = (asset_a, asset_b)
        self.valid_name = valid_pair_name[self.pair]
        self.letter = letter

        ### INVERSION FLAGS ###
        # if inversion is true, we want to buy the base asset of that pair -- else sell the base asset of that pair
        self.inversion = self.valid_name.startswith(asset_b)

        # base asset is what the pair name starts with, quote asset is what follows
        self.base_asset = asset_a if self.valid_name.startswith(asset_a) else asset_b
        self.quote_asset = asset_b if self.valid_name.startswith(asset_a) else asset_a

        ### ORDER TYPE: 'MARKET' OR 'LIMIT' ###
        self.order_type = order_type

        ### ORDER DIRECTION: 'BUY' OR 'SELL ###
        self.order_direction = 'BUY' if self.inversion else 'SELL'

        ### COEFFICIENT TYPE: 'BEST_BID' OR 'BEST_ASK' ###
        # Determine whether to get the best bid or the best ask for each trade
        if self.order_type == 'LIMIT':
            # place an order at good price
            # TODO: the prices of limit orders can be optimized by an estimation/prediction function
            self.coefficient_type = 'BEST_BID' if (self.order_direction == 'BUY') else 'BEST_ASK'
        else:  # type == 'MARKET'
            self.coefficient_type = 'BEST_ASK' if (self.order_direction == 'BUY') else 'BEST_BID'


        ### FOR REVERTING LIMIT ORDERS ###
        self.rev_order_type = 'MARKET' # might not be necessary to define this since it doesn't change
        self.rev_order_direction = 'SELL' if self.inversion else 'BUY'
        self.rev_coefficient_type = 'BEST_ASK' if (self.rev_order_direction == 'BUY') else 'BEST_BID'


        ### DATA STRUCTURES ###
        self.trade_window = trade_window
        self.trades = []
        self.bids = []
        self.asks = []

        self.most_recent_trade = None

        # using these values as heuristics for best bid/ask
        self.most_recent_ask = None
        self.most_recent_bid = None

        ### Transforms ###
        self.np_prices = np.array([]) # using numpy array for easier calculations
        self.mean = None
        self.std_dev = None

        ### Backtesting ###
        self.prev_bt_trade_id = None

        ### Asset information from Binance ###
        self.min_notional, self.step_size, self.tick_size = self.get_asset_info()

    def get_asset_info(self):
        # TODO: might want to get the rest of the asset info, but this will do for now
        asset_info = list(filter(lambda x: x['baseAsset']==self.base_asset and x['quoteAsset']==self.quote_asset,
                                 exchange_info['symbols']))[0]
        min_notional = str(list(filter(lambda x: x['filterType']=='MIN_NOTIONAL',asset_info['filters']))[0]['minNotional'])
        step_size = str(list(filter(lambda x: x['filterType']=='LOT_SIZE',asset_info['filters']))[0]['stepSize'])
        tick_size = str(list(filter(lambda x: x['filterType']=='PRICE_FILTER',asset_info['filters']))[0]['tickSize'])
        return min_notional, step_size, tick_size

    def update_transforms(self):
        self.mean = np.mean(self.np_prices)
        self.std_dev = np.std(self.np_prices)
        return

    def add_backtest_row(self, row):
        # to be called only by the Backtester class
        # updates bid and ask queues based on new backtest data row
        letter = self.letter

        sub_row = {k: row[1][k] for k in [letter+'_price',
                                          letter+'_quantity',
                                          letter+'_trade_id',
                                          letter+'_is_buyer_maker']}

        if sub_row[letter+'_trade_id'] != self.prev_bt_trade_id:
            self.most_recent_trade = sub_row
            self.trades.append(sub_row)

            self.prev_bt_trade_id = self.trades[-1][letter+'_trade_id']
            self.trades = self.trades[-self.trade_window:]

            # append to np prices array so we can make calculations on price data
            self.np_prices = np.append(self.np_prices, float(sub_row[letter+'_price']))[-self.trade_window:]
            # make calculations on price data
            self.update_transforms()

            # TODO: this is most likely right, but might want to confirm this correctly categorizes bids and asks
            # TIP: use the print_bids_asks function?
            if sub_row[letter+'_is_buyer_maker'] > 0:
                self.most_recent_bid = sub_row
                self.bids.append(sub_row)
                self.bids = self.bids[-self.trade_window:]
            else:
                self.most_recent_ask = sub_row
                self.asks.append(sub_row)
                self.asks = self.asks[-self.trade_window:]

        return

    def get_trade_info(self, asset_a_amount):
        # calculate info for the trade we would place at the current time

        # this doesn't have to be a function, but it is for now until I can decide how I want to get the price

        # TODO: the prices of limit orders can be optimized by an estimation/prediction function
        if self.coefficient_type == 'BEST_BID':
            price = float(self.most_recent_bid[self.letter+'_price'])
        else:
            price = float(self.most_recent_ask[self.letter+'_price'])

        # TODO: validate values to the asset info filters (i.e. making sure nominal_total meets minimum amount, etc.)
        # TODO: decide what to do if inputs do not meet filters

        if self.inversion:
            # place a BUY order
            # here, we know the total and need to calculate the quantity

            nominal_total = float(asset_a_amount)

            qty = nominal_total / price
            rounded_qty = Decimal(qty).quantize(Decimal(self.step_size), rounding=ROUND_FLOOR)
            trade_total = float(rounded_qty) * float(price)
            truncated_amount = nominal_total - trade_total # in units of asset_a
            result = float(rounded_qty) # the amount received of the next asset in the sequence
        else:
            # place a SELL order
            # here, we know the quantity and need to calculate the total

            qty = asset_a_amount
            rounded_qty = Decimal(qty).quantize(Decimal(self.step_size), rounding=ROUND_FLOOR)
            truncated_amount = float(qty) - float(rounded_qty) # in units of asset_a
            trade_total = float(rounded_qty) * price
            result = float(trade_total) # the amount received of the next asset in the sequence

        # trading fees heuristic
        result = result * 0.9995

        # the info required to place the order through the API
        order_object = OrderObject(
            letter=self.letter,
            pair_name=self.valid_name,
            order_type=self.order_type,
            order_direction=self.order_direction,
            symbol=self.valid_name,
            quantity=float(rounded_qty),
            price=str(price),
            trade_total=trade_total,
            truncated_amount=truncated_amount,
            result=result
        )

        return order_object

    def get_reverted_trade_info(self, order_to_revert):
        # TODO: BACKTEST ONLY -- for a realtime system, make sure to record the actual execution price
        # gather information to create an order that reverts a previous order (the input order object)
        # NOTE: reverting a trade must be done with a market order

        if self.rev_coefficient_type == 'BEST_BID':
            price = float(self.most_recent_bid[self.letter+'_price'])
        else:
            price = float(self.most_recent_ask[self.letter+'_price'])

        qty = order_to_revert.result
        rounded_qty = Decimal(qty).quantize(Decimal(self.step_size), rounding=ROUND_FLOOR)
        truncated_amount = float(qty) - float(rounded_qty)  # in units of result (asset_b)
        trade_total = float(rounded_qty) * price

        if self.inversion:
            result = float(trade_total)
        else:
            result = float(rounded_qty)

        # trading fees heuristic
        result = result * 0.9995

        # the info required to place the order through the API
        order_object = OrderObject(
            letter=self.letter,
            pair_name=self.valid_name,
            order_type=self.rev_order_type,
            order_direction=self.rev_order_direction,
            symbol=self.valid_name,
            quantity=float(rounded_qty),
            price=str(price),
            trade_total=trade_total,
            truncated_amount=truncated_amount,
            result=result
        )

        return order_object

    def print_trade_FIFO(self):
        # for debugging
        print(self.trades)
        return

    def print_bids_asks(self):
        # for debugging
        print(self.bids)
        print(self.asks)
        print()

class OrderObject():
    def __init__(self, letter, pair_name, order_type, order_direction, symbol, price, quantity, trade_total,
                 truncated_amount, result, status='PENDING'):
        self.letter = letter
        self.pair_name = pair_name

        self.order_type = order_type
        self.order_direction = order_direction
        self.symbol = symbol
        self.quantity = quantity
        self.price = price

        self.trade_total = trade_total
        self.truncated_amount = truncated_amount

        self.result = result

        self.status = status

        return

class Backtester:
    def __init__(self, trade_window=50):
        ### HARD CODED
        self.asset_a = 'USDT'
        self.asset_b = 'BNB'
        self.asset_c = 'BCC'
        order_type_a = 'LIMIT'
        order_type_b = 'MARKET'
        order_type_c = 'LIMIT'
        self.base_amount= 500.0 # amount of asset_a we are trading with

        # using self.trade_amount as the quantity for each order
        # TODO: not used???
        self.trade_amount = self.base_amount
        self.prev_order_result = None # Continuously store the result of the previous trade

        ### SET UP HANDLES FOR EACH TRADING PAIR
        self.pair_a = valid_pair_name[(self.asset_a, self.asset_b)]
        self.pair_b = valid_pair_name[(self.asset_b, self.asset_c)]
        self.pair_c = valid_pair_name[(self.asset_c, self.asset_a)]
        self.pair_names = {'a': self.pair_a,
                           'b': self.pair_b,
                           'c': self.pair_c}
        self.trading_pairs = {self.pair_a: TradingPair(
                                  asset_a=self.asset_a,
                                  asset_b=self.asset_b,
                                  order_type=order_type_a,
                                  letter='a',
                                  trade_window=trade_window),
                              self.pair_b: TradingPair(
                                  asset_a=self.asset_b,
                                  asset_b=self.asset_c,
                                  order_type=order_type_b,
                                  letter='b',
                                  trade_window=trade_window),
                              self.pair_c: TradingPair(
                                  asset_a=self.asset_c,
                                  asset_b=self.asset_a,
                                  order_type=order_type_c,
                                  letter='c',
                                  trade_window=trade_window)}

        self.current_row = None

        #self.trade_in_place = False # True when there is an arbitrage trade in the pipeline
        self.current_order = None

        self.order_queue = [] # The next trade in the sequence
        self.filled_orders = [] # Keep track of placed orders in the current sequence in case we need to revert them

        self.ledger = [] # Keep track of all filled orders after their sequence is complete

        if os.path.isfile('backtest_df_oldstyle.p'):
            with open('backtest_df_oldstyle.p', 'rb') as in_file:
                self.df = pickle.load(in_file)
        else:
            self.df = generate_df()

        ### DATA STRUCTURES FOR METRICS ###

        # calculate account value in units of base currency and plot it over time at the end
        # TODO: account_size is only updated at the end of an arbitrage sequence or when sequence is cancelled
        self.account_size = self.base_amount
        self.account_size_over_time = []

        self.trade_time_elapsed = 0
        self.trade_timeout = 30 # seconds

        # TODO: implement accounts data structure and keep track of truncated trade quantities (min step size)

        return

    def run_backtest(self, debug_plot=False):
        # TODO: this is where we should modify the data structures for the performance metrics
        print("running backtest!")
        debug_iter = 0
        for row in self.df.iterrows():
            self.process_row(row)
            self.step()
            self.account_size_over_time.append(self.account_size)

            debug_iter+=1
            if debug_iter > 9000:
                break

        if debug_plot:
            plt.plot(self.account_size_over_time)
            plt.show()

        #print([order.result for order in self.filled_orders])
        #print(len(self.filled_orders))
        print(self.account_size_over_time)
        return

    def process_row(self, row):
        # only add if trade id is different from the most recent bid/ask
        # if most recent bid/ask doesn't exist (len==0) then add anyways
        self.current_row = row

        for key, value in self.pair_names.items():
            self.trading_pairs[value].add_backtest_row(row)

        return

    def step(self, debug=False):
        # run this once for each row of dataframe
        #time.sleep(0.01)

        self.account_size_over_time.append(self.account_size)

        if self.current_order == None and len(self.order_queue) != 0:
            self.current_order = self.order_queue.pop(0)

        order_in_place = (self.current_order != None)

        if order_in_place:

            # check the status of the order
            order_status = self.current_order.status

            if order_status == 'PENDING':

                # We have a pending stage for orders to simulate the time it takes to get the order through to Binance
                # TODO: optionally just skip the pending stage and make it active immediately
                # order has just arrived from the queue, place it immediately
                if self.current_order.order_type == 'LIMIT':
                    print('placing limit order!')
                    self.place_limit_order(self.current_order)
                elif self.current_order.order_type == 'MARKET':
                    print('placing market order!')
                    # if self.current_order.order_type == 'MARKET'
                    self.place_market_order(self.current_order)
                else:
                    print('UNEXPECTED ORDER TYPE:', str(self.current_order.order_type))
                    exit(1)
                return

            elif order_status == 'ACTIVE':
                # limit order is active and waiting to be filled
                print('order is active!')

                # i.e. price falls above/below limit and fills order
                meets_fill_conditions = self.check_order_is_filled(self.current_order)

                if meets_fill_conditions or debug:
                    # we've met the conditions that fill an order (immediately) for debugging purposes
                    print('order has been filled!')

                    self.current_order.status = 'FILLED'

                    self.prev_order_result = self.current_order.result
                    self.record_filled_order(self.current_order)
                    self.process_after_filled_order()
                    print('ACCOUNT SIZE:', self.account_size)

                    return
                else:
                    # run a "timer" for active orders -- revert the trade sequence if it overruns the timeout
                    self.trade_time_elapsed += 1
                    timeout = self.check_limit_order_timeout()
                    if timeout:
                        print('LIMIT ORDER TIMED OUT!')
                        #exit(1)
                        # TODO: check logic for elif order_status == 'CANCELED':
                        self.cancel_current_order()
                        self.revert_sequence_orders()
                    return

            elif order_status == 'FILLED':
                # right now, this condition is only reached after a market order is filled
                print('REACHED order_status==FILLED')
                print('order_queue:', self.order_queue)

                self.prev_order_result = self.current_order.result
                self.record_filled_order(self.current_order)
                self.process_after_filled_order()
                print('ACCOUNT SIZE:', self.account_size)

            elif order_status == 'CANCELED':
                # something has gone wrong -- revert the arbitrage sequence
                # TODO: look into the nature of any cancellations that could happen
                # TODO: test this -- NOT SURE under which conditions a trade would even be canceled
                print('Order was canceled -- this is an unexpected condition')
                exit(1)

                # It would make sense to revert in a realtime trading situation, but we have to first understand
                # what the full nature of the cancellation before we decide if that's a good idea
                # self.revert_sequence_orders()
                return
        else:
            # there is currently no trade in the pipeline
            # check if trade conditions have been met
            impl_profit_cond = self.check_impl_profit_conditions()
            #lstm_cond = self.check_lstm_conditions()
            #cond = impl_profit_cond and lstm_cond
            cond = impl_profit_cond # debug
            if cond:
                # Calculate the fields for the arbitrage sequence and queue up the trades
                # Then place the first order immediately (in the next step?)

                self.queue_up_trade_sequence()
                self.current_order = self.order_queue.pop(0)

                return
            else:
                # go to next row
                return

    def record_filled_order(self, order_object):
        # record an order that has been filled by adding it to the filled_orders queue
        self.filled_orders.append(order_object)
        return

    def process_after_filled_order(self):
        if len(self.order_queue) != 0:
            # 2. update current order to be the next one
            self.current_order = self.order_queue.pop(0)
        else:
            # 2. update account size
            self.account_size = self.current_order.result
            # 3. move filled orders to ledger
            # 4. clear filled orders
            self.move_filled_to_ledger()
            # 5. clear current order (= None)
            self.current_order = None

        return

    def revert_sequence_orders(self):
        # clear order queue and revert all orders that have been made so far in the current sequence
        # this is triggered by a limit order timeout
        # TODO
        print('REVERTING SEQUENCE ORDERS')

        self.order_queue = []

        reverted_current_order = self.trading_pairs[self.current_order.pair_name].get_reverted_trade_info(self.current_order)
        self.current_order = None

        for order in reversed(self.filled_orders):
            reverted_order = self.trading_pairs[order.pair_name].get_reverted_trade_info(order)
            self.order_queue.append(reverted_order)

        self.filled_orders = []

        print('SEQUENCE REVERTED')
        return

    def cancel_current_order(self):
        # cancel the current limit order
        # this is triggered by a limit order timeout
        # TODO: in real-time situation, this would trigger an API call

        self.current_order.status = 'CANCELED'
        pass

    def place_limit_order(self, order_object):
        # normally, this is where we would place the order through the API
        order_object.status = 'ACTIVE'
        self.trade_time_elapsed = 0
        return

    def place_market_order(self, order_object):
        # normally, this is where we would place the order through the API
        # TODO: keep track of execution price (and result) -- which is not the same as the "result" attribute of the order_object

        # TODO: execution price HERE

        # Update self.current_order so that the price matches the execution price

        letter = order_object.letter
        row = self.current_row
        sub_row = {k: row[1][k] for k in [letter + '_price',
                                          letter + '_quantity',
                                          letter + '_trade_id',
                                          letter + '_is_buyer_maker']}
        pair_name = order_object.pair_name



        trade_size = self.prev_order_result
        print('MARKET ORDER TRADE SIZE: ', trade_size)
        print('PAIR NAME:', pair_name)


        executed_order_object = self.trading_pairs[pair_name].get_trade_info(trade_size)

        self.current_order = executed_order_object
        self.current_order.status = 'FILLED'

        # Update any subsequent orders in the arbitrage sequence so that their trade sizes scale to the market order
        # TODO: IMPORTANT implement updating of subsequent orders
        self.update_subsequent_orders_to_current_market_order()
        pass

        #self.prev_order_result= self.current_order.result

        #self.record_filled_order(self.current_order)

        #self.process_after_filled_order()

        return

    def update_subsequent_orders_to_current_market_order(self):
        # update subsequent orders in the order queue so that the input matches the result of the market order
        # TODO
        pass
        return

    def check_limit_order_timeout(self):
        if self.trade_time_elapsed > self.trade_timeout:
            return True
        else:
            return False

    def check_order_is_filled(self, order_object):
        # check if the market meets the conditions to fill the current active order
        # returns true if an active order is filled, false if still active
        # TODO: only fill an order if there is a large enough quantity to fill it -- using a heuristic for now

        letter = order_object.letter

        row = self.current_row

        sub_row = {k: row[1][k] for k in [letter + '_price',
                                          letter + '_quantity',
                                          letter + '_trade_id',
                                          letter + '_is_buyer_maker']}

        if order_object.order_type == 'LIMIT':
            if order_object.order_direction == 'BUY':
                if sub_row[letter+'_price'] < order_object.price:
                    return True
                else:
                    return False
            elif order_object.order_direction == 'SELL':
                if sub_row[letter+'_price'] > order_object.price:
                    return True
                else:
                    return False
        elif order_object.order_type == 'MARKET':
            # for now, this condition is unreachable unless I change the design
            # TODO: did you change the design to meet this unreachable code?
            pass
        else:
            # TODO: this is kinda stupid, remove this
            print('IMPROPER TYPE?')
            exit(1)

    def move_filled_to_ledger(self):
        while len(self.filled_orders) != 0:
            order = self.filled_orders.pop(0)
            self.ledger.append(order)

    def queue_up_trade_sequence(self, debug=False):

        trade_size_a = self.account_size
        order_object_a = self.trading_pairs[self.pair_a].get_trade_info(trade_size_a)
        print('trade a result:', order_object_a.result, order_object_a.pair_name)

        trade_size_b = order_object_a.result
        order_object_b = self.trading_pairs[self.pair_b].get_trade_info(trade_size_b)
        print('trade b result:', order_object_b.result, order_object_b.pair_name)

        trade_size_c = order_object_b.result
        order_object_c = self.trading_pairs[self.pair_c].get_trade_info(trade_size_c)
        print('trade c result:', order_object_c.result, order_object_c.pair_name)

        if not debug:
            print('queueing up trade sequence!')
            self.order_queue.append(order_object_a)
            self.order_queue.append(order_object_b)
            self.order_queue.append(order_object_c)

        trade_result = order_object_c.result


    def check_impl_profit_conditions(self):
        # return true if we should initiate an arbitrage sequence, else false

        bids_a, asks_a = self.trading_pairs[self.pair_a].bids, self.trading_pairs[self.pair_a].asks
        if len(bids_a) == 0:
            return False
        bid_a = bids_a[-1]['a_price']
        #ask_a = asks_a[-1]['a_price']
        #mean_a = self.trading_pairs[self.pair_a].mean
        #std_dev_a = self.trading_pairs[self.pair_a].std_dev

        bids_b, asks_b = self.trading_pairs[self.pair_b].bids, self.trading_pairs[self.pair_b].asks
        if len(asks_b) == 0:
            return False
        #bid_b = bids_b[-1]['b_price']
        ask_b = asks_b[-1]['b_price']
        #mean_b = self.trading_pairs[self.pair_b].mean
        #std_dev_b = self.trading_pairs[self.pair_b].std_dev

        bids_c, asks_c = self.trading_pairs[self.pair_c].bids, self.trading_pairs[self.pair_c].asks
        if len(asks_c) == 0:
            return False
        #bid_c = bids_c[-1]['c_price']
        ask_c = asks_c[-1]['c_price']
        #mean_c = self.trading_pairs[self.pair_c].mean
        #std_dev_c = self.trading_pairs[self.pair_c].std_dev

        implicit_result = (1.0 / float(bid_a)) * (1.0 / float(ask_b)) * float(ask_c) * self.base_amount * 0.9985


        if implicit_result > self.base_amount:
            print('Implicit trade result fwd:', implicit_result-self.base_amount)
            return True

        return False

    def check_lstm_conditions(self):
        # TODO: implement LSTM predictor for A and C
        print("this is where you predict the price direction with the LSTM model")
        return False

print("TUAN -- ROLL OUT!")
print("Don't give up!")
print("Let's get rich!")

bt = Backtester()
bt.run_backtest()
