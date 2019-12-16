from binance.client import Client
from ValidPairName import *
import static_exchange_info

#from binance.websockets import BinanceSocketManager

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


class TradingPair():
    # Holds information for an asset pair
    def __init__(self, asset_a, asset_b, order_type):
        self.pair = (asset_a, asset_b)
        self.valid_name = valid_pair_name[self.pair]

        # if inversion is true, we want to buy the base asset of that pair -- else sell the base asset of that pair
        # this decides which asset of the two is more relevant when an operation is performed on this trading pair
        self.inversion = self.valid_name.startswith(asset_b)

        # base asset is what the pair name starts with, quote asset is what follows
        self.base_asset = asset_a if self.valid_name.startswith(asset_a) else asset_b
        self.quote_asset = asset_b if self.valid_name.startswith(asset_a) else asset_a

        self.order_type = order_type # 'MARKET' OR 'LIMIT'

        self.order_direction = 'BUY' if self.inversion else 'SELL'

        # Determine whether to get the best bid or the best ask for each trade
        # This is the coefficient used for calculating the implicit arbitrage profit
        if self.order_type == 'LIMIT':
            # place an order at good price
            # TODO: the prices of limit orders can be optimized by an estimation/prediction function
            self.coefficient_type = 'BEST_BID' if (self.order_direction == 'BUY') else 'BEST_ASK'
        else:  # type == 'MARKET'
            self.coefficient_type = 'BEST_ASK' if (self.order_direction == 'BUY') else 'BEST_BID'

        ### FOR REVERTING LIMIT ORDERS ###
        self.rev_order_direction = 'SELL' if self.inversion else 'BUY'
        self.rev_coefficient_type = 'BEST_ASK' if (self.rev_order_direction == 'BUY') else 'BEST_BID'

        ### Asset information from Binance ###
        self.min_notional, self.step_size, self.tick_size = self.get_asset_info()

        return

    def get_asset_info(self):
        # TODO: might want to get the rest of the asset info, but this will do for now
        asset_info = list(filter(lambda x: x['baseAsset']==self.base_asset and x['quoteAsset']==self.quote_asset,
                                 static_exchange_info.exchange_info['symbols']))[0]
        min_notional = str(list(filter(lambda x: x['filterType']=='MIN_NOTIONAL',asset_info['filters']))[0]['minNotional'])
        step_size = str(list(filter(lambda x: x['filterType']=='LOT_SIZE',asset_info['filters']))[0]['stepSize'])
        tick_size = str(list(filter(lambda x: x['filterType']=='PRICE_FILTER',asset_info['filters']))[0]['tickSize'])
        return min_notional, step_size, tick_size


class Order():
    # Holds information for a limit/market order
    def __init__(self, pair_name, order_type, order_direction, symbol, price, quantity, trade_total,
                 truncated_amount, starting_amount, resulting_amount, starting_asset, resulting_asset,
                 sequence_direction, timeout=20, status='PENDING'):
        self.pair_name = pair_name

        self.order_type = order_type # 'MARKET' OR 'LIMIT'
        self.order_direction = order_direction # 'BUY' OR 'SELL'
        self.symbol = symbol
        self.quantity = quantity
        self.price = price

        self.trade_total = trade_total
        self.truncated_amount = truncated_amount

        self.starting_amount = starting_amount
        self.resulting_amount = resulting_amount

        self.starting_asset = starting_asset
        self.resulting_asset = resulting_asset

        self.timeout = timeout # seconds
        self.timer = 0

        self.status = status # 'PENDING', 'ACTIVE', 'FILLED', OR 'CANCELED'

        self.price_slippage = None # for market orders

        self.executed_qty = 0 # amount of the order that is filled

        self.sequence_direction = sequence_direction # 'FORWARD' OR 'REVERSE'

        return

    def __str__(self):
        return 'Symbol: %s, Type: %s, Price: %s, Qty: %s' % (self.symbol, self.order_type, self.price, self.quantity)


class BacktestExchangeInterface():
    # simulates data from the exchange
    def __init__(
        self,
        asset_a='USDT',
        asset_b='BNB',
        asset_c='BCC',
        asset_a_init_amount=500.0,
        dataframe_pickle='backtest_df.p'):

        self.asset_a = asset_a
        self.asset_b = asset_b
        self.asset_c = asset_c
        self.pair_a = valid_pair_name[(self.asset_a, self.asset_b)]
        self.pair_b = valid_pair_name[(self.asset_b, self.asset_c)]
        self.pair_c = valid_pair_name[(self.asset_c, self.asset_a)]

        if os.path.isfile(dataframe_pickle):
            with open(dataframe_pickle, 'rb') as in_file:
                self.df = pickle.load(in_file)
        else:
            self.df = self.generate_dataframe(pair_a=self.pair_a,
                                              pair_b=self.pair_b,
                                              pair_c=self.pair_c)

        #self.df_iterator = self.df.iterrows()

        self.current_row = None

        self.account_balances = {self.asset_a: asset_a_init_amount, self.asset_b: 0.0, self.asset_c: 0.0}

        #self.open_orders_by_symbol = {}

        return

    def generate_dataframe(self, pair_a, pair_b, pair_c):
        data_file_a = '../data/%s_backtest_3.csv' % pair_a
        data_file_b = '../data/%s_backtest_3.csv' % pair_b
        data_file_c = '../data/%s_backtest_3.csv' % pair_c

        df_a = pd.read_csv(
            data_file_a,
            header=0,
            index_col='trade_time',
            names=[
                pair_a + '_event_time',  # E
                pair_a + '_ignore',  # M
                'trade_time',  # T
                pair_a + '_seller_order_id',  # a
                pair_a + '_buyer_order_id',  # b
                pair_a + '_event_type',  # e
                pair_a + '_is_buyer_maker',  # m
                pair_a + '_price',  # p
                pair_a + '_quantity',  # q
                pair_a + '_symbol',  # s
                pair_a + '_trade_id'  # t
            ]
        )

        # drop useless columns
        df_a = df_a.drop(
            columns=[
                pair_a + '_buyer_order_id',
                pair_a + '_seller_order_id',
                pair_a + '_event_time',
                pair_a + '_ignore',
                pair_a + '_symbol',
                pair_a + '_event_type'
            ]
        )

        # get rid of the stupid = signs I accidentally put in the data
        df_a = df_a.applymap(lambda x: x.split('=')[-1])

        df_a.index = df_a.index.map(lambda x: x.split('=')[-1])

        # format data
        df_a.index = pd.to_datetime(df_a.index, unit='ms')
        df_a[pair_a + '_price'] = df_a[pair_a + '_price'].values
        df_a[pair_a + '_quantity'] = df_a[pair_a + '_quantity'].values
        df_a[pair_a + '_trade_id'] = df_a[pair_a + '_trade_id'].values
        # map strings to boolean values
        df_a[pair_a + '_is_buyer_maker'] = df_a[pair_a + '_is_buyer_maker'].map({'False': -1, 'True': 1})

        # df_a = df_a.drop_duplicates(keep='last')

        df_a = df_a.resample('s').last().fillna(value=None, method='ffill')

        df_b = pd.read_csv(
            data_file_b,
            header=0,
            index_col='trade_time',
            names=[
                pair_b + '_event_time',  # E
                pair_b + '_ignore',  # M
                'trade_time',  # T
                pair_b + '_seller_order_id',  # a
                pair_b + '_buyer_order_id',  # b
                pair_b + '_event_type',  # e
                pair_b + '_is_buyer_maker',  # m
                pair_b + '_price',  # p
                pair_b + '_quantity',  # q
                pair_b + '_symbol',  # s
                pair_b + '_trade_id'  # t
            ]
        )
        # drop useless columns
        df_b = df_b.drop(
            columns=[
                pair_b + '_buyer_order_id',
                pair_b + '_seller_order_id',
                pair_b + '_event_time',
                pair_b + '_ignore',
                pair_b + '_symbol',
                pair_b + '_event_type'
            ]
        )

        # get rid of the stupid = signs I accidentally put in the data
        df_b = df_b.applymap(lambda x: x.split('=')[-1])

        df_b.index = df_b.index.map(lambda x: x.split('=')[-1])

        # format data
        df_b.index = pd.to_datetime(df_b.index, unit='ms')
        df_b[pair_b + '_price'] = df_b[pair_b + '_price'].values
        df_b[pair_b + '_quantity'] = df_b[pair_b + '_quantity'].values
        df_b[pair_b + '_trade_id'] = df_b[pair_b + '_trade_id'].values

        # map strings to boolean values
        df_b[pair_b + '_is_buyer_maker'] = df_b[pair_b + '_is_buyer_maker'].map({'False': -1, 'True': 1})

        # df_b = df_b.drop_duplicates(keep='last')

        df_b = df_b.resample('s').last().fillna(value=None, method='ffill')

        df_c = pd.read_csv(
            data_file_c,
            header=0,
            index_col='trade_time',
            names=[
                pair_c + '_event_time',  # E
                pair_c + '_ignore',  # M
                'trade_time',  # T
                pair_c + '_seller_order_id',  # a
                pair_c + '_buyer_order_id',  # b
                pair_c + '_event_type',  # e
                pair_c + '_is_buyer_maker',  # m
                pair_c + '_price',  # p
                pair_c + '_quantity',  # q
                pair_c + '_symbol',  # s
                pair_c + '_trade_id'  # t
            ]
        )
        # drop useless columns
        df_c = df_c.drop(
            columns=[
                pair_c + '_buyer_order_id',
                pair_c + '_seller_order_id',
                pair_c + '_event_time',
                pair_c + '_ignore',
                pair_c + '_symbol',
                pair_c + '_event_type'
            ]
        )

        # get rid of the stupid = signs I accidentally put in the data
        df_c = df_c.applymap(lambda x: x.split('=')[-1])

        df_c.index = df_c.index.map(lambda x: x.split('=')[-1])

        # format data
        df_c.index = pd.to_datetime(df_c.index, unit='ms')
        df_c[pair_c + '_price'] = df_c[pair_c + '_price'].values
        df_c[pair_c + '_quantity'] = df_c[pair_c + '_quantity'].values
        df_c[pair_c + '_trade_id'] = df_c[pair_c + '_trade_id'].values

        # map strings to boolean values
        df_c[pair_c + '_is_buyer_maker'] = df_c[pair_c + '_is_buyer_maker'].map({'False': -1, 'True': 1})

        # df_c = df_c.drop_duplicates(keep='last')

        df_c = df_c.resample('s').last().fillna(value=None, method='ffill')


        df = df_a.join(df_c, how='outer')
        df = df.join(df_b, how='outer')

        df = df.dropna()

        with open('backtest_df.p', 'wb') as out_file:
            pickle.dump(df, out_file)

        return df

    #def get_next_row(self):
    #    self.current_row = next(self.df_iterator)
    #    return self.current_row

    #def place_order(self, order_object):
    #    if order_object.pair_name in self.open_orders_by_symbol:
    #        self.open_orders_by_symbol[order_object.pair_name].append(order_object)
    #    else:
    #        self.open_orders_by_symbol[order_object.pair_name] = [order_object]
    #    return

    #def get_all_open_orders(self):
    #    return self.open_orders_by_symbol

    #def get_all_orders(self, pair_name):
    #    return self.open_orders_by_symbol[pair_name]

    #def check_order_status(self):
    #    pass

    #def cancel_order(self):
    #    pass

    #def get_account_balance(self, asset):
    #    return self.account_balances[asset]


class ArbitrageTrader:
    def __init__(
        self,
        asset_a='USDT',
        asset_b='BNB',
        asset_c='BCC',
        order_type_a='LIMIT',
        order_type_b='MARKET',
        order_type_c='LIMIT',
        asset_a_init_amount=500.0,
        trade_window=50):

        self.exchange_interface = BacktestExchangeInterface(
            asset_a='USDT',
            asset_b='BNB',
            asset_c='BCC',
            asset_a_init_amount=asset_a_init_amount,
            dataframe_pickle='backtest_df.p')

        self.asset_a = asset_a
        self.asset_b = asset_b
        self.asset_c = asset_c
        self.order_type_a = order_type_a
        self.order_type_b = order_type_b
        self.order_type_c = order_type_c
        self.pair_a = valid_pair_name[(self.asset_a, self.asset_b)]
        self.pair_b = valid_pair_name[(self.asset_b, self.asset_c)]
        self.pair_c = valid_pair_name[(self.asset_c, self.asset_a)]
        self.pair_names = {'a': self.pair_a,
                           'b': self.pair_b,
                           'c': self.pair_c}

        self.trading_pairs = {self.pair_a: TradingPair(asset_a, asset_b, order_type_a),
                              self.pair_b: TradingPair(asset_b, asset_c, order_type_b),
                              self.pair_c: TradingPair(asset_c, asset_a, order_type_c)}

        self.trade_window = trade_window

        ### DYNAMIC
        self.current_row = None

        self.trades = {self.pair_a: [], self.pair_b: [], self.pair_c: []}
        self.bids = {self.pair_a: [], self.pair_b: [], self.pair_c: []}
        self.asks = {self.pair_a: [], self.pair_b: [], self.pair_c: []}
        self.np_prices = {self.pair_a: np.array([]), self.pair_b: np.array([]), self.pair_c: np.array([])}

        self.mean = {self.pair_a: None, self.pair_b: None, self.pair_c: None}
        self.std_dev = {self.pair_a: None, self.pair_b: None, self.pair_c: None}

        # only append row to trades data structure if trade_id is different from the most recent
        self.most_recent_trade_id = {self.pair_a: None, self.pair_b: None, self.pair_c: None}
        self.most_recent_bid = {self.pair_a: None, self.pair_b: None, self.pair_c: None}
        self.most_recent_ask = {self.pair_a: None, self.pair_b: None, self.pair_c: None}

        self.trade_size = self.exchange_interface.account_balances[asset_a]

        self.pending_orders = []
        self.filled_orders = []
        self.current_order = None # current active order

        self.account_size_over_time = []
        self.order_ledger = []
        self.completed_sequences = []
        self.reverted_sequences = []

        self.market_order_slippage = []
        self.active_order_times = []

        self.state_dict = {
            'POLLING': self.Polling(context=self),
            'PAIR_A_FORWARD': self.PairAForwardIsActive(context=self),
            'PAIR_B_FORWARD': self.PairBForwardIsActive(context=self),
            'PAIR_C_FORWARD': self.PairCForwardIsActive(context=self),
            'PAIR_A_REVERSE': self.PairAReverseIsActive(context=self),
            'PAIR_B_REVERSE': self.PairBReverseIsActive(context=self),
            'PAIR_C_REVERSE': self.PairCReverseIsActive(context=self)}

        self.state = 'POLLING'

        self.sequence_is_active = False

        return


    class State():
        def __init__(self, context):
            self.context = context
        def transition_to_state(self, state_name):
            print('Entering state: ', state_name)
            self.context.state = state_name


    class ActiveLimitOrder(State):
        def check_fill_conditions(self): # boolean
            return self.context.check_limit_order_fill()

        def record_filled_order(self):
            self.context.record_filled_limit_order()
            return

        def place_next_order(self):
            self.context.place_next_order()
            return

        def increment_timer(self):
            self.context.current_order.timer += 1
            return

        def check_timeout(self): # boolean
            # TODO: use timestamps instead of incrementing a timer

            ### DEBUG -- forcing a timeout to test the reverted sequence
            if self.context.current_order.pair_name == 'BCCUSDT':
                return True


            return self.context.current_order.timer > self.context.current_order.timeout

        def get_order_fill_amount(self): # float
            # TODO: actually implement this -- get executedQty from current order
            debug_val = 0.0
            return debug_val

        def was_a_partial_fill(self, fill_amount): # boolean
            # return True if order was more than 0% filled before it was canceled, else False
            # TODO: you can use the Python Binance API to check for 'PARTIALLY_FILLED' or 'FILLED'
            # TODO: check for qty filled, currently just using False as a heuristic
            debug_heuristic = False
            return debug_heuristic

        def cancel_active_sequence(self):
            self.context.cancel_active_sequence()
            return

        def queue_up_reverting_sequence(self):
            self.context.queue_up_reverting_sequence()
            return

        def record_completed_sequence(self):
            self.context.record_completed_sequence()
            return


    class ActiveMarketOrder(State):
        def check_fill_conditions(self): # boolean
            # just in case it doesn't fill immediately
            return self.context.check_market_order_fill()
        def record_filled_order(self):
            self.context.record_filled_market_order()
            return
        def place_next_order(self):
            self.context.place_next_order()
            return
        def record_reverted_sequence(self):
            self.context.record_reverted_sequence()
            return
        def record_completed_sequence(self):
            self.context.record_completed_sequence()
            return
        def update_sequence_after_market_order(self):
            self.context.update_sequence_after_market_order()
            return


    class Polling(State):
        def loop(self):
            trading_condition = self.check_arbitrage_condition()

            if trading_condition:
                self.queue_up_arbitrage_sequence()
                self.place_next_order()
                self.transition_to_state('PAIR_A_FORWARD')
            return

        def check_arbitrage_condition(self): # boolean
            return self.context.check_arbitrage_conditions()

        def queue_up_arbitrage_sequence(self):
            self.context.queue_up_arbitrage_sequence()
            return

        def place_next_order(self):
            self.context.place_next_order()
            return


    class PairAForwardIsActive(ActiveLimitOrder):
        def loop(self):
            order_filled = self.check_fill_conditions()

            if order_filled:
                self.record_filled_order()
                self.place_next_order()
                self.transition_to_state('PAIR_B_FORWARD')
            else:
                timeout = self.check_timeout()

                if timeout:
                    self.cancel_active_sequence()

                    current_executed_qty = self.get_order_fill_amount()
                    partial_fill = self.was_a_partial_fill(current_executed_qty)

                    if partial_fill:
                        self.queue_up_reverting_sequence()
                        self.place_next_order()
                        self.transition_to_state('PAIR_A_REVERSE')
                    else:
                        self.transition_to_state('POLLING')
                else:
                    self.increment_timer()
            return


    class PairBForwardIsActive(ActiveMarketOrder):
        def loop(self):
            order_filled = self.check_fill_conditions()

            if order_filled:
                self.record_filled_order()
                self.place_next_order()
                self.transition_to_state('PAIR_C_FORWARD')
            return


    class PairCForwardIsActive(ActiveLimitOrder):
        def loop(self):
            order_filled = self.check_fill_conditions()

            if order_filled:
                self.record_filled_order()
                self.record_completed_sequence()
                self.transition_to_state('POLLING')
            else:
                timeout = self.check_timeout()

                if timeout:
                    print('order timed out!')
                    self.cancel_active_sequence()

                    current_executed_qty = self.get_order_fill_amount()
                    partial_fill = self.was_a_partial_fill(current_executed_qty)

                    if partial_fill:
                        # TODO: make a more robust decision to wait and/or cancel & place market order if halfway filled
                        self.queue_up_reverting_sequence()
                        self.place_next_order()
                        self.transition_to_state('PAIR_C_REVERSE')
                    else:
                        self.queue_up_reverting_sequence()
                        self.place_next_order()
                        self.transition_to_state('PAIR_B_REVERSE')
            return


    class PairAReverseIsActive(ActiveMarketOrder):
        def loop(self):
            order_filled = self.check_fill_conditions()

            if order_filled:
                self.record_filled_order()
                self.record_reverted_sequence()
                self.transition_to_state('POLLING')
            return


    class PairBReverseIsActive(ActiveMarketOrder):
        def loop(self):
            order_filled = self.check_fill_conditions()

            if order_filled:
                self.record_filled_order()
                self.place_next_order()
                self.transition_to_state('PAIR_A_REVERSE')
            return


    class PairCReverseIsActive(ActiveMarketOrder):
        def loop(self):
            order_filled = self.check_fill_conditions()

            if order_filled:
                self.record_filled_order()
                self.place_next_order()
                self.transition_to_state('PAIR_B_REVERSE')
            return


    def run_backtest(self):
        i = 0
        for row in self.exchange_interface.df.iterrows():
            self.current_row = row
            self.backtest_loop()

        #self.plot_price_slippage()
        #self.plot_active_order_times()
        #self.plot_account_size_over_time()
        return

    def backtest_loop(self):
        self.process_row_data()
        self.state_dict[self.state].loop()
        return

    def process_row_data(self):
        for letter, pair_name in self.pair_names.items():
            sub_row = {k: self.current_row[1][k] for k in [
                pair_name+'_price',
                pair_name+'_quantity',
                pair_name+'_trade_id',
                pair_name+'_is_buyer_maker']}
            if sub_row[pair_name+'_trade_id'] != self.most_recent_trade_id[pair_name]:
                self.trades[pair_name].append(sub_row)
                self.trades[pair_name] = self.trades[pair_name][-self.trade_window:]
                self.most_recent_trade_id[pair_name] = self.trades[pair_name][-1][pair_name+'_trade_id']

                self.np_prices[pair_name] = np.append(
                    self.np_prices[pair_name],
                    float(sub_row[pair_name+'_price']))[-self.trade_window:]

                self.mean[pair_name] = np.mean(self.np_prices[pair_name])
                self.std_dev[pair_name] = np.std(self.np_prices[pair_name])

                if sub_row[pair_name+'_is_buyer_maker'] > 0:
                    self.most_recent_bid[pair_name] = sub_row
                    self.bids[pair_name].append(sub_row)
                    self.bids[pair_name] = self.bids[pair_name][-self.trade_window:]
                else:
                    self.most_recent_ask[pair_name] = sub_row
                    self.asks[pair_name].append(sub_row)
                    self.asks[pair_name] = self.asks[pair_name][-self.trade_window:]
        return

    def check_arbitrage_conditions(self):
        # return true if we should queue up and initiate an arbitrage trade sequence
        if len(self.bids[self.pair_a]) == 0:
            return False
        bid_a = self.bids[self.pair_a][-1][self.pair_a+'_price']

        if len(self.asks[self.pair_b]) == 0:
            return False
        ask_b = self.asks[self.pair_b][-1][self.pair_b+'_price']

        if len(self.asks[self.pair_c]) == 0:
            return False
        ask_c = self.asks[self.pair_c][-1][self.pair_c+'_price']

        implicit_result = (1.0 / float(bid_a)) * (1.0 / float(ask_b)) * float(ask_c) * self.trade_size * 0.9985

        if implicit_result > self.trade_size:
            print('Implicit trade result fwd:', implicit_result-self.trade_size)
            return True

        return False

    def queue_up_arbitrage_sequence(self):
        if self.sequence_is_active:
            print('Unexpectedly tried to queue up trade sequence when a sequence was already active')
            exit(1)

        if len(self.pending_orders) > 0:
            print('Unexpectedly tried to queue up trade sequence when there are orders in self.pending_orders')
            exit(1)

        self.trade_size = self.exchange_interface.account_balances[self.asset_a]

        trade_size_a = self.trade_size
        if self.trading_pairs[self.pair_a].inversion:
            order_object_a = self.create_order(self.pair_a, sequence_direction='FORWARD', qty=trade_size_a)
        else:
            order_object_a = self.create_order(self.pair_a, sequence_direction='FORWARD', total=trade_size_a)
        print('trade a result:', order_object_a.resulting_amount, order_object_a.resulting_asset)

        trade_size_b = order_object_a.resulting_amount
        if self.trading_pairs[self.pair_b].inversion:
            order_object_b = self.create_order(self.pair_b, sequence_direction='FORWARD', qty=trade_size_b)
        else:
            order_object_b = self.create_order(self.pair_b, sequence_direction='FORWARD', total=trade_size_b)
        print('trade b result:', order_object_b.resulting_amount, order_object_b.resulting_asset)

        trade_size_c = order_object_b.resulting_amount
        if self.trading_pairs[self.pair_b].inversion:
            order_object_c = self.create_order(self.pair_c, sequence_direction='FORWARD', qty=trade_size_c)
        else:
            order_object_c = self.create_order(self.pair_c, sequence_direction='FORWARD', total=trade_size_c)
        print('trade c result:', order_object_c.resulting_amount, order_object_c.resulting_asset)

        print('queueing up trade sequence!')
        self.pending_orders.append(order_object_a)
        self.pending_orders.append(order_object_b)
        self.pending_orders.append(order_object_c)

        trade_result = order_object_c.resulting_amount

        return

    def cancel_active_sequence(self):
        print('canceling current sequence')
        self.current_order.status = 'CANCELED'

        self.sequence_is_active = False

        self.pending_orders = []
        print('order and sequence canceled\n\n\n')

        self.print_account()

        return

    def queue_up_reverting_sequence(self):
        print('REVERTING SEQUENCE')

        if self.sequence_is_active:
            print('Unexpectedly tried to queue up trade sequence without canceling the previous sequence first')
            exit(1)
        else:
            self.sequence_is_active = False

        if self.current_order.executed_qty != 0:
            print('the current order was partially filled, then canceled, so the system is creating a trade to revert it')
            print('THIS IS NOT EXPECTED TO HAPPEN SINCE PARTIAL FILLS IS NOT IMPLEMENTED YET')
            exit(1)
            #reverted_current_order = self.revert_forward_order(self.current_order)
            reverted_current_order = self.create_order(self.current_order.pair_name,
                                                       sequence_direction='REVERSE',
                                                       qty=self.current_order.executed_qty)
            self.pending_orders.append(reverted_current_order)
        else:
            print('the current order was not filled at all, then canceled, so there is no need to revert it')
        self.current_order = None

        for order in reversed(self.filled_orders):
            reverted_order = self.create_order(order.pair_name, sequence_direction='REVERSE', qty=order.executed_qty)
            self.pending_orders.append(reverted_order)
        self.filled_orders = []

        print('SEQUENCE REVERTED')

        return

    def place_next_order(self):
        self.sequence_is_active = True
        self.current_order = self.pending_orders.pop(0)
        self.current_order.status = 'ACTIVE'
        return

    def create_order(self, pair_name, sequence_direction='FORWARD', qty=None, total=None, price=None):
        print('pair name:', pair_name)

        trading_pair = self.trading_pairs[pair_name]

        if not price:
            print('USING MOST RECENT PRICE FOR THIS ORDER OBJECT')
            if sequence_direction == 'FORWARD':
                if trading_pair.coefficient_type == 'BEST_BID':
                    price = float(self.most_recent_bid[pair_name][pair_name+'_price'])
                else:
                    price = float(self.most_recent_ask[pair_name][pair_name+'_price'])
            elif sequence_direction == 'REVERSE':
                if trading_pair.rev_coefficient_type == 'BEST_BID':
                    price = float(self.most_recent_bid[pair_name][pair_name+'_price'])
                else:
                    price = float(self.most_recent_ask[pair_name][pair_name+'_price'])
            else:
                print('unsupported sequence direction')
                exit(1)
        else:
            print('PRICE WAS PASSSED')
            print('I ASSUME YOU WOULD PASS PRICE IF YOU WANT TO UPDATE OR REVERT LIMIT ORDERS')
            exit(1)

        if total and qty == None:
            print('known total, unknown quantity')
            # total is always in units of quote asset
            if sequence_direction == 'FORWARD':
                if trading_pair.order_direction == 'BUY':
                    nominal_total = total

                    qty = nominal_total / price
                    rounded_qty = Decimal(qty).quantize(Decimal(trading_pair.step_size), rounding=ROUND_FLOOR)
                    trade_total = float(rounded_qty) * float(price)
                    truncated_amount = nominal_total - trade_total

                    starting_amount = float(trade_total)
                    starting_asset = trading_pair.quote_asset

                    resulting_amount = float(rounded_qty)
                    resulting_asset = trading_pair.base_asset

                    resulting_amount = resulting_amount * 0.9995  # 0.05% trading fee heuristic

                    order_object = Order(
                        pair_name=trading_pair.valid_name,
                        order_type=trading_pair.order_type,
                        order_direction=trading_pair.order_direction,
                        symbol=trading_pair.valid_name,
                        quantity=float(rounded_qty),
                        price=str(price),
                        trade_total=trade_total,
                        truncated_amount=truncated_amount,
                        starting_amount=starting_amount,
                        resulting_amount=resulting_amount,
                        starting_asset=starting_asset,
                        resulting_asset=resulting_asset,
                        sequence_direction=sequence_direction
                    )

                    return order_object

                elif trading_pair.order_direction == 'SELL':
                    # Perhaps there are no cases where this condition happens?
                    print('UNEXPECTED CONDITION: creating a forward sell order with known total')
                    exit(1)
            elif sequence_direction == 'REVERSE':
                if trading_pair.rev_order_direction == 'BUY':
                    # Perhaps there are no cases where this condition happens?
                    print('UNEXPECTED CONDITION: creating a reverse buy order order with known total')
                    exit(1)
                    pass
                elif trading_pair.rev_order_direction == 'SELL':
                    # Perhaps there are no cases where this condition happens?
                    print('UNEXPECTED CONDITION: creating a reverse sell order with known total')
                    exit(1)
            else:
                print('unsupported sequence direction')
                exit(1)

        elif qty and total == None:
            print('known quantity, unknown total')
            # quantity is always in units of base asset

            if sequence_direction == 'FORWARD':
                if trading_pair.order_direction == 'BUY':
                    # Perhaps there are no cases where this condition happens?
                    print('UNEXPECTED CONDITION: creating a forward buy order with known qty')
                    print('qty: ', str(qty))
                    print('total: ', str(total))
                    exit(1)
                elif trading_pair.order_direction == 'SELL':
                    rounded_qty = Decimal(qty).quantize(Decimal(trading_pair.step_size), rounding=ROUND_FLOOR)
                    truncated_amount = float(qty) - float(rounded_qty)
                    trade_total = float(rounded_qty) * price

                    starting_amount = float(rounded_qty)
                    starting_asset = trading_pair.base_asset

                    resulting_amount = float(trade_total)
                    resulting_asset = trading_pair.quote_asset

                    resulting_amount = resulting_amount * 0.9995  # 0.05% trading fee heuristic

                    order_object = Order(
                        pair_name=trading_pair.valid_name,
                        order_type=trading_pair.order_type,
                        order_direction=trading_pair.order_direction,
                        symbol=trading_pair.valid_name,
                        quantity=float(rounded_qty),
                        price=str(price),
                        trade_total=trade_total,
                        truncated_amount=truncated_amount,
                        starting_amount=starting_amount,
                        resulting_amount=resulting_amount,
                        starting_asset=starting_asset,
                        resulting_asset=resulting_asset,
                        sequence_direction=sequence_direction
                    )

                    return order_object

            elif sequence_direction == 'REVERSE':
                # you would use this function to pass the executed quantity of a partially or fully filled order
                # so make sure, outside of this function, to update the executed_qty field

                order_type = 'MARKET'  # assumes that all reverting orders are market orders

                if trading_pair.rev_order_direction == 'BUY':
                    rounded_qty = Decimal(qty).quantize(Decimal(trading_pair.step_size), rounding=ROUND_FLOOR)
                    truncated_amount = float(qty) - float(rounded_qty)
                    trade_total = float(rounded_qty) * price

                    starting_amount = float(trade_total)
                    starting_asset = trading_pair.quote_asset

                    resulting_amount = float(rounded_qty)
                    resulting_asset = trading_pair.base_asset

                    resulting_amount = resulting_amount * 0.9995  # 0.05% trading fee heuristic

                    order_object = Order(
                        pair_name=trading_pair.valid_name,
                        order_type=order_type,
                        order_direction=trading_pair.rev_order_direction,
                        symbol=trading_pair.valid_name,
                        quantity=float(rounded_qty),
                        price=str(price),
                        trade_total=trade_total,
                        truncated_amount=truncated_amount,
                        starting_amount=starting_amount,
                        resulting_amount=resulting_amount,
                        starting_asset=starting_asset,
                        resulting_asset=resulting_asset,
                        sequence_direction=sequence_direction
                    )

                    return order_object


                elif trading_pair.rev_order_direction == 'SELL':
                    rounded_qty = Decimal(qty).quantize(Decimal(trading_pair.step_size), rounding=ROUND_FLOOR)
                    truncated_amount = float(qty) - float(rounded_qty)
                    trade_total = float(rounded_qty) * price

                    starting_amount = float(rounded_qty)
                    starting_asset = trading_pair.base_asset

                    resulting_asset = trading_pair.quote_asset
                    resulting_amount = float(trade_total)

                    resulting_amount = resulting_amount * 0.9995  # 0.05% trading fee heuristic

                    order_object = Order(
                        pair_name=trading_pair.valid_name,
                        order_type=order_type,
                        order_direction=trading_pair.rev_order_direction,
                        symbol=trading_pair.valid_name,
                        quantity=float(rounded_qty),
                        price=str(price),
                        trade_total=trade_total,
                        truncated_amount=truncated_amount,
                        starting_amount=starting_amount,
                        resulting_amount=resulting_amount,
                        starting_asset=starting_asset,
                        resulting_asset=resulting_asset,
                        sequence_direction=sequence_direction
                    )

                    return order_object
            else:
                print('unsupported sequence direction')
                exit(1)

        else:
            print('unsupported use of this function: pass arguments for at least qty or total, but not both')
            exit(1)

    def update_order_fill_amount(self, order_to_update):
        # TODO: do this
        pass

    def check_limit_order_fill(self):
        # TODO: check for full quantity fill instead of just price
        # TODO: use the update_order_fill_amount method to update fill based on "order book"

        market_price = float(self.current_row[1][self.current_order.pair_name + '_price'])
        execution_price = float(self.current_order.price)

        if self.current_order.order_direction == 'BUY':
            if market_price < execution_price:
                return True
            else:
                return False
        elif self.current_order.order_direction == 'SELL':
            if market_price > execution_price:
                return True
            else:
                return False
        else:
            print('ERROR: unexpected order direction!')
            exit(1)

    def check_market_order_fill(self):
        # just in case it doesn't fill immediately for some reason
        return True

    def record_filled_limit_order(self):
        self.current_order.status = 'FILLED'
        self.current_order.executed_qty = self.current_order.quantity

        # record result into order ledger
        self.filled_orders.append(self.current_order)
        self.order_ledger.append(self.current_order)
        # record result into exchange_interface.account_balances
        self.exchange_interface.account_balances[self.current_order.starting_asset] -= self.current_order.starting_amount
        self.exchange_interface.account_balances[self.current_order.resulting_asset] += self.current_order.result
        print('limit order result: %s %s' % (self.current_order.result, self.current_order.resulting_asset))
        print('time to fill: %s seconds' % self.current_order.timer)

        self.active_order_times.append(self.current_order.timer)

        return

    def record_filled_market_order(self):
        sequence_direction = self.current_order.sequence_direction

        self.current_order.status = 'PROCESSED_NOT_FILLED' # this order object is not the one that gets filled

        # this assume that the current order was completely filled
        # TODO: it's possible we will have to move this line to a more appropriate function
        self.current_order.executed_qty = self.current_order.quantity

        if sequence_direction=='FORWARD':
            if self.trading_pairs[self.current_order.pair_name].inversion:
                executed_order = self.create_order(self.current_order.pair_name,
                                                   sequence_direction=sequence_direction,
                                                   qty=self.current_order.quantity)
            else:
                executed_order = self.create_order(self.current_order.pair_name,
                                                   sequence_direction=sequence_direction,
                                                   total=self.current_order.trade_total)
        elif sequence_direction=='REVERSE':
            executed_order = self.create_order(self.current_order.pair_name,
                                               sequence_direction=sequence_direction,
                                               qty=self.current_order.quantity)
        else:
            print('UNSUPPORTED SEQUENCE DIRECTION')
            exit(1)


        calculated_order = self.current_order
        self.current_order = executed_order
        self.current_order.status = 'FILLED'
        self.current_order.executed_qty = self.current_order.quantity

        market_price = float(self.current_order.price)
        arbitrage_price = float(calculated_order.price)

        if self.current_order.order_direction == 'BUY':
            self.current_order.price_slippage = market_price - arbitrage_price
        elif self.current_order.order_direction == 'SELL':
            self.current_order.price_slippage = arbitrage_price - market_price
        else:
            print('ERROR: unexpected order direction!')
            exit(1)

        # record result into order ledger
        self.filled_orders.append(self.current_order)
        self.order_ledger.append(self.current_order)
        # record price slippage in ledger as a backtesting metric
        self.market_order_slippage.append(self.current_order.price_slippage)
        # record result into exchange_interface.account_balances
        self.exchange_interface.account_balances[self.current_order.starting_asset] -= self.current_order.starting_amount
        self.exchange_interface.account_balances[self.current_order.resulting_asset] += self.current_order.resulting_amount
        print('market order result: %s %s' % (self.current_order.resulting_amount, self.current_order.resulting_asset))
        print('price slippage: %s %s' % (self.current_order.price_slippage, self.current_order.starting_asset))

        executed_result = executed_order.resulting_amount

        self.update_sequence_after_market_order(executed_result)

        return

    def update_sequence_after_market_order(self, market_order_result):
        prev_result = market_order_result
        updated_pending_orders = []

        for old_order in self.pending_orders:
            pair_name = old_order.pair_name
            order_type = old_order.order_type
            sequence_direction = old_order.sequence_direction
            price = old_order.price

            if order_type=='LIMIT':
                if sequence_direction=='FORWARD':
                    if self.trading_pairs[pair_name].inversion:
                        updated_order = self.create_order(pair_name,
                                                          sequence_direction=sequence_direction,
                                                          total=prev_result,
                                                          price=price)
                    else:
                        updated_order = self.create_order(pair_name,
                                                          sequence_direction=sequence_direction,
                                                          qty=prev_result,
                                                          price=price)
                else:
                    print('UNEXPECTED ORDER DIRECTION WHILE UPDATING SEQUENCE')
                    exit(1)
            elif order_type=='MARKET':
                if sequence_direction=='FORWARD':
                    if self.trading_pairs[pair_name].inversion:
                        updated_order = self.create_order(pair_name,
                                                          sequence_direction=sequence_direction,
                                                          total=prev_result)
                    else:
                        updated_order = self.create_order(pair_name,
                                                          sequence_direction=sequence_direction,
                                                          qty=prev_result)
                elif old_order.sequence_direction=='REVERSE':
                    if self.trading_pairs[pair_name].inversion:
                        updated_order = self.create_order(pair_name,
                                                          sequence_direction=sequence_direction,
                                                          qty=prev_result)
                    else:
                        updated_order = self.create_order(pair_name,
                                                          sequence_direction=sequence_direction,
                                                          total=prev_result)
                else:
                    print('UNEXPECTED SEQUENCE DIRECTION')
                    exit(1)
            else:
                print('UNEXPECTED ORDER TYPE')
                exit(1)
            updated_pending_orders.append(updated_order)
            prev_result = updated_order.resulting_amount

        self.pending_orders = updated_pending_orders

        return

    def record_reverted_sequence(self):
        # TODO: think about what you want to do for this

        if len(self.pending_orders) > 0:
            print('Unexpectedly tried to record a completed sequence when there is still an order in pending_orders')
            exit(1)

        # record into account_size_over_time
        self.account_size_over_time.append((self.current_row[0], self.exchange_interface.account_balances[self.asset_a]))

        self.print_account()

        self.sequence_is_active = False
        pass

    def record_completed_sequence(self):
        if len(self.pending_orders) > 0:
            print('Unexpectedly tried to record a completed sequence when there is still an order in pending_orders')
            exit(1)

        self.filled_orders = []

        # record into account_size_over_time
        self.account_size_over_time.append((self.current_row[0], self.exchange_interface.account_balances[self.asset_a]))

        self.print_account()

        self.sequence_is_active = False
        return

    def print_account(self):
        print('Asset a in account: {: f}'.format(self.exchange_interface.account_balances[self.asset_a]))
        print('Asset b in account: {: f}'.format(self.exchange_interface.account_balances[self.asset_b]))
        print('Asset c in account: {: f}'.format(self.exchange_interface.account_balances[self.asset_c]))
        print('\n\n')
        return

    def plot_price_slippage(self):
        plt.scatter(range(len(self.market_order_slippage)), self.market_order_slippage)
        plt.show()
        return

    def plot_active_order_times(self):
        plt.scatter(range(len(self.active_order_times)), self.active_order_times)
        plt.show()
        return

    def plot_account_size_over_time(self):
        plt.plot(*zip(*self.account_size_over_time))
        plt.show()
        return

trader = ArbitrageTrader(asset_a='USDT',
                         asset_b='BNB',
                         asset_c='BCC',
                         order_type_a='LIMIT',
                         order_type_b='MARKET',
                         order_type_c='LIMIT',
                         asset_a_init_amount=1000.0)
trader.run_backtest()
