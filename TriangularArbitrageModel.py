import grequests
import os
from datetime import datetime, timedelta
from binance.client import Client
from binance.enums import *
from ValidPairName import *
import time
import PeriodicScheduler

# Every feature of the arbitrage trading system should be defined in this model

class TriangularArbitrageModel:
    def __init__(self, asset_a, asset_b, asset_c, order_type_a, order_type_b, order_type_c):
        self.api_key = os.environ.get('STELLA_API_KEY')
        self.secret_key = os.environ.get('STELLA_SECRET_KEY')

        # Construct the Binance API client
        self.client = Client(self.api_key, self.secret_key)

        ### CURRENCY PAIR HANDLES ###
        self.asset_a = asset_a
        self.asset_b = asset_b
        self.asset_c = asset_c
        self.pair_a = (asset_a, asset_b)
        self.pair_b = (asset_b, asset_c)
        self.pair_c = (asset_c, asset_a)
        self.pair_a_valid_name = valid_pair_name[self.pair_a]
        self.pair_b_valid_name = valid_pair_name[self.pair_b]
        self.pair_c_valid_name = valid_pair_name[self.pair_c]

        # The price coefficient is determined from two factors: inversion and order type

        ### INVERSION FLAGS ###
        # if inversion is true, sell the base asset of that pair -- else buy the base asset of that pair
        self.trade_a_inversion = self.pair_a_valid_name.startswith(asset_a)
        self.trade_b_inversion = self.pair_b_valid_name.startswith(asset_b)
        self.trade_c_inversion = self.pair_c_valid_name.startswith(asset_c)

        ### ORDER TYPE: 'MARKET' OR 'LIMIT' ###
        self.order_type_a = order_type_a
        self.order_type_b = order_type_b
        self.order_type_c = order_type_c

        ### ORDER DIRECTION: 'BUY' OR 'SELL ###
        self.order_direction_a = 'BUY' if self.trade_a_inversion else 'SELL'
        self.order_direction_b = 'BUY' if self.trade_b_inversion else 'SELL'
        self.order_direction_c = 'BUY' if self.trade_c_inversion else 'SELL'

        ### COEFFICIENT TYPE: 'BEST_BID' OR 'BEST_ASK'
        # Determine whether to get the best bid or the best ask for each trade
        if self.order_type_a == 'LIMIT':
            self.coefficient_type_a = 'BEST_BID' if (self.order_direction_a == 'BUY') else 'BEST_ASK'
        else: # type == 'MARKET'
            self.coefficient_type_a = 'BEST_ASK' if (self.order_direction_a == 'BUY') else 'BEST_BID'

        if self.order_type_b == 'LIMIT':
            self.coefficient_type_b = 'BEST_BID' if (self.order_direction_a == 'BUY') else 'BEST_ASK'
        else: # type == 'MARKET'
            self.coefficient_type_b = 'BEST_ASK' if (self.order_direction_a == 'BUY') else 'BEST_BID'

        if self.order_type_c == 'LIMIT':
            self.coefficient_type_c = 'BEST_BID' if (self.order_direction_a == 'BUY') else 'BEST_ASK'
        else: # type == 'MARKET'
            self.coefficient_type_c = 'BEST_ASK' if (self.order_direction_a == 'BUY') else 'BEST_BID'

        ### ORDER BOOKS ###
        # call update_order_books to update the data
        self.order_book_limit = 100
        self.pair_a_order_book = {}
        self.pair_b_order_book = {}
        self.pair_c_order_book = {}

        self.recent_trades = []

        ### TRADE TIME ESTIMATES ###
        self.trade_a_time_est = 0
        self.trade_b_time_est = 0
        self.trade_c_time_est = 0

        ### TRADE ESTIMATES ###
        # amount of the asset (n+1) received from making trade n, calculated from most recent order book
        # call update_trade_estimates to update the data
        self.trade_a_received = 0
        self.trade_b_received = 0
        self.trade_c_received = 0 # resulting amount of base asset after finishing trades

        ### TRADE ESTIMATES ###
        # TODO: change data type of initial values to match intended use
        self.trade_a_best_order_est = 0
        self.trade_b_best_order_est = 0
        self.trade_c_best_order_est = 0

        # TODO: deprecate these? -- these are used in limit order calculation
        self.trade_b_best_price_est = 0
        self.trade_c_best_price_est = 0
        self.trade_a_best_price_est = 0

        ### DEBOUNCE ###
        self.debounce = timedelta(0, 10, 0) # 10 seconds -- decrease this when we get more advanced
        # initialize last_trade_time so we can trade immediately
        self.last_trade_time = datetime.now() - self.debounce

        ### INDICATORS ###
        # TODO: add a prefix 'v_' to all vector indicators
        # max length of indicator vectors
        self.ind_window = 60
        # keep track of the last N prices for each pair
        self.ind_prices_a = []
        self.ind_prices_b = []
        self.ind_prices_c = []
        # keep track of the last N calculated order fill amounts
        # TODO: rename these
        self.ind_trade_a_received = []
        self.ind_trade_b_received = []
        self.ind_trade_c_received = []
        self.ind_trade_c_received_len = 0
        # TODO: if necessary, implement the trade c average as a vector, not a scalar
        self.ind_trade_c_received_rolling_sma = 0
        self.ind_trade_c_received_rolling_window = 10  # smaller window to calculate for trading strategy

        self.recent_trades_a = []
        self.recent_trades_b = []
        self.recent_trades_c = []
        self.recent_bids_a = []
        self.recent_asks_a = []
        self.recent_bids_b = []
        self.recent_asks_b = []
        self.recent_bids_c = []
        self.recent_asks_c = []

        ### ASSET EXCHANGE INFO ###
        # call update_exchange_info to update data
        self.pair_a_minQty = 0
        self.pair_a_maxQty = 0
        self.pair_a_stepSize = 0
        self.pair_b_minQty = 0
        self.pair_b_maxQty = 0
        self.pair_b_stepSize = 0
        self.pair_c_minQty = 0
        self.pair_c_maxQty = 0
        self.pair_c_stepSize = 0
        self.exchange_info = {}

        ### ACCOUNT INFO ###
        # call update_account_info to update and print data
        self.asset_a_account = 0
        self.asset_b_account = 0
        self.asset_c_account = 0
        self.account_info = {}

        ### OTHER ###
        self.trade_fee = 0.0005 # used to estimate trade result

        ### TRADE CONDITIONALS ###
        # only make trades when these conditionals evaluate to True
        # call update_debounce_conditional to update
        self.debounce_conditional = (datetime.now() - self.last_trade_time >= self.debounce)
        # call update_trade_conditional to update
        self.trade_conditional = False

        ### CALL INITIAL FUNCTIONS ###
        self.update_exchange_info()
        self.update_account_info()
        # TODO: possibly deprecate update_recent_trades() function and replace with socket stream implementation
        self.update_recent_trades()

    def async_update(self, asset_a_qty, profit_threshold):
        # This method should be called periodically for executing live trading
        self.update_order_books()

        #self.update_trade_estimates(asset_a_qty)

        #self.update_implied_trade_data()

        #TODO: replacing this function with 'update_implied_trade_data'
        #self.update_trade_estimates_limit_order(asset_a_qty)

        self.update_debounce_conditional()

        # TODO: add price direction predictions to trade conditions
        # TODO: add estimate time to fulfill limit orders to trade conditions
        # TODO: use ML to estimate time to fulfill limit order
        self.update_trade_conditional(profit_threshold)

        self.update_indicators()

        self.trade(asset_a_qty)

        return

    def update_recent_trades(self, n=50):
        self.recent_trades_a = self.client.get_recent_trades(symbol=self.pair_a_valid_name, limit=n)
        self.recent_trades_b = self.client.get_recent_trades(symbol=self.pair_b_valid_name, limit=n)
        self.recent_trades_c = self.client.get_recent_trades(symbol=self.pair_c_valid_name, limit=n)

        self.recent_bids_a = []
        self.recent_asks_a = []
        for trade in self.recent_trades_a:
            if trade['isBuyerMaker']:
                self.recent_bids_a.append(trade)
            else:
                self.recent_asks_a.append(trade)

        self.recent_bids_b = []
        self.recent_asks_b = []
        for trade in self.recent_trades_b:
            if trade['isBuyerMaker']:
                self.recent_bids_b.append(trade)
            else:
                self.recent_asks_b.append(trade)

        self.recent_bids_c = []
        self.recent_asks_c = []
        for trade in self.recent_trades_c:
            if trade['isBuyerMaker']:
                self.recent_bids_c.append(trade)
            else:
                self.recent_asks_c.append(trade)

    def update_trade_time_estimates(self):
        # Estimate the time until the next trade
        # TODO: use machine learning to estimate this
        now = int(time.time() * 1000)

        time_delta_a = now - self.recent_trades_a[-11]['time']  # in ms
        frequency_a = (float(len(self.recent_trades_a[-11:-1])) / time_delta_a)  # trades / ms
        self.trade_a_time_est = 1.0 / frequency_a

        time_delta_b = now - self.recent_trades_b[-11]['time']  # in ms
        frequency_b = (float(len(self.recent_trades_b[-11:-1])) / time_delta_b)  # trades / ms
        self.trade_b_time_est = 1.0 / frequency_b

        time_delta_c = now - self.recent_trades_c[-11]['time']  # in ms
        frequency_c = (float(len(self.recent_trades_c[-11:-1])) / time_delta_c)  # trades / ms
        self.trade_c_time_est = 1.0 / frequency_c
        return

    def update_predicted_trade_directions(self):
        # TODO: implement class attributes for each pair (even though we might not care about all 3)
        pass
        return

    def update_exchange_info(self):
        # Get/update exchange info, which includes min and max trade qty and price resolution for all assets
        self.exchange_info = self.client.get_exchange_info()

        for symbol in self.exchange_info['symbols']:
            if symbol['symbol'] == self.pair_a_valid_name:
                self.pair_a_minQty = symbol['filters'][1]['minQty']
                self.pair_a_maxQty = symbol['filters'][1]['maxQty']
                self.pair_a_stepSize = symbol['filters'][1]['stepSize']

        for symbol in self.exchange_info['symbols']:
            # print(symbol['filters'])
            if symbol['symbol'] == self.pair_b_valid_name:
                self.pair_b_minQty = symbol['filters'][1]['minQty']
                self.pair_b_maxQty = symbol['filters'][1]['maxQty']
                self.pair_b_stepSize = symbol['filters'][1]['stepSize']

        for symbol in self.exchange_info['symbols']:
            # print(symbol['filters'])
            if symbol['symbol'] == self.pair_c_valid_name:
                self.pair_c_minQty = symbol['filters'][1]['minQty']
                self.pair_c_maxQty = symbol['filters'][1]['maxQty']
                self.pair_c_stepSize = symbol['filters'][1]['stepSize']

    def update_account_info(self):
        # Get/update account info, particularly balance for each asset
        # We can check if a trade has been made by checking change in balance
        self.account_info = self.client.get_account(recvWindow=10000)
        for balance in self.account_info['balances']:
            if balance['asset'] == self.asset_a:
                print(balance['asset'], balance)
                print(balance['free'])
                print('Change %s: %s' % (balance['asset'], float(balance['free']) - float(self.asset_a_account)))
                self.asset_a_account = float(balance['free'])
            elif balance['asset'] == self.asset_b:
                print(balance['asset'], balance)
                print(balance['free'])
                print('Change %s: %s' % (balance['asset'], float(balance['free']) - float(self.asset_b_account)))
                self.asset_b_account = float(balance['free'])
            elif balance['asset'] == self.asset_c:
                print(balance['asset'], balance)
                print('Change %s: %s' % (balance['asset'], float(balance['free']) - float(self.asset_c_account)))
                self.asset_c_account = float(balance['free'])

    def update_order_books(self):
        # Get/update order book data in parallel
        ep = 'https://api.binance.com/api/v1/depth'
        symbols = [self.pair_a_valid_name, self.pair_b_valid_name, self.pair_c_valid_name]
        headers = {'X-MBX-APIKEY': self.api_key}

        get_request_list = []
        for symbol in symbols:
            get_request_list.append(grequests.get(
                    ep,
                    params={'symbol': symbol, 'limit': self.order_book_limit},
                    headers=headers
            ))

        responses = grequests.map(get_request_list, exception_handler=self._request_exception, size=3)

        pair_a_response = responses[0]
        pair_b_response = responses[1]
        pair_c_response = responses[2]

        if 429 in [pair_a_response.status_code, pair_b_response.status_code, pair_c_response.status_code]:
            print('Error while updating order books:')
            print('Received a status code 429... exiting')
            exit(1)

        self.pair_a_order_book = pair_a_response.json()
        self.pair_b_order_book = pair_b_response.json()
        self.pair_c_order_book = pair_c_response.json()

        return

    def update_trade_estimates_limit_order(self, asset_a_qty):
        # TODO: replace this function
        # WARNING: DEPRECATED - This does not calculate the proper trading strategy
        # calculate the estimates for trade profit from current order book data - this implies a specific strategy
        trade_a_result_est = self.get_trade_received_limit(self.pair_a_order_book, asset_a_qty, self.trade_a_inversion)
        self.trade_a_received = self.truncate(trade_a_result_est[0], self.pair_a_stepSize)
        self.trade_a_best_order_est = trade_a_result_est[1]
        self.trade_a_best_price_est = trade_a_result_est[1][0]
        print('self.trade_a_received: ', self.trade_a_received)

        trade_b_result_est = self.get_trade_received_limit(self.pair_b_order_book, self.trade_a_received, self.trade_b_inversion)
        self.trade_b_received = self.truncate(trade_b_result_est[0], self.pair_b_stepSize)
        self.trade_b_best_order_est = trade_b_result_est[1]
        self.trade_b_best_price_est = trade_b_result_est[1][0]
        print('self.trade_b_received: ', self.trade_b_received)

        trade_c_result_est = self.get_trade_received_limit(self.pair_c_order_book, self.trade_b_received, self.trade_c_inversion)
        self.trade_c_received = self.truncate(trade_c_result_est[0], self.pair_c_stepSize)
        self.trade_c_best_order_est = trade_c_result_est[1]
        self.trade_c_best_price_est = trade_c_result_est[1][0]
        print('self.trade_c_received: ', self.trade_c_received)
        return

    def update_debounce_conditional(self):
        self.debounce_conditional = (datetime.now() - self.last_trade_time >= self.debounce)
        return

    def update_trade_conditional(self, profit_threshold):
        # TODO: ensure the following conditionals:
        # - implied profit is higher than a specified threshold
        # - predicted price change is past a certain threshold in the right direction for all limit order trades
        # - estimated time to complete each trade is within a specified limit
        self.trade_conditional = (self.trade_c_received > self.ind_trade_c_received_rolling_sma > profit_threshold)
        return

    def update_indicators(self):
        self.ind_trade_a_received = []
        self.ind_trade_b_received = []
        self.ind_trade_c_received = []
        self.ind_trade_c_received_len = 0
        self.ind_trade_c_received_rolling_window = 10  # smaller window to calculate for trading strategy
        self.ind_window = 60

        # update the time series for last n implicit profits
        self.ind_trade_c_received_len = len(self.ind_trade_c_received)

        if self.ind_trade_c_received_len >= self.ind_window:
            self.ind_trade_a_received.pop(0)
            self.ind_trade_b_received.pop(0)
            self.ind_trade_c_received.pop(0)
        self.ind_trade_a_received.append(self.trade_a_received)
        self.ind_trade_b_received.append(self.trade_b_received)
        self.ind_trade_c_received.append(self.trade_c_received)

        self.ind_trade_c_received_rolling_sma = self.trade_c_received
        if self.ind_trade_c_received_len > self.ind_trade_c_received_rolling_window:
            self.ind_trade_c_received_rolling_sma = sum(self.ind_trade_c_received[-self.ind_trade_c_received_rolling_window:]) / float(self.ind_trade_c_received_rolling_window)
        return

    #def trade(self, asset_a_qty):
    #    if self.debounce_conditional and self.trade_conditional:
    #        print()
    #        print('Hypothetical Trade C Result: ', self.trade_c_received)
    #        print('self.ind_trade_c_received_rolling_sma: ', self.ind_trade_c_received_rolling_sma)
    #        pre_trade = datetime.now()
    #        print('Placing arbitrage trades: ', str(pre_trade))
    #        # self.place_arbitrage_trade()
    #        post_trade = datetime.now()
    #        print('Arbitrage trades complete: ', str(post_trade))
    #        print('Time to complete trades: ', str(post_trade-pre_trade))
    #        print()
    #        self.last_trade_time = post_trade
#
    #    else:
    #        print('Trade conditional not met. Hypothetical Trade C Result: ', self.trade_c_received - asset_a_qty) # profit is trade c result - asset_a
    #    return

    def get_trade_received(self, order_book, input_qty, inversion):
        if inversion:
            result = self.estimate_sell_order_result(order_book, input_qty)
            return result * (1.0 - self.trade_fee)
        result = self.estimate_buy_order_result(order_book, input_qty)
        return result * (1.0 - self.trade_fee)

    @staticmethod
    def estimate_sell_order_result(order_book, input_qty):
        # TODO: truncate with step size here
        # use this if inversion for the trade is True
        # input_qty should be amount of the base asset, the result from the previous trade
        # return the TOTAL quote asset resulting from selling against the order book

        # amount = total_base * price

        base_to_sell = input_qty
        quote_bought = 0.0

        for bid in order_book['bids']:
            price = float(bid[0])
            qty = float(bid[1])
            bid_total = price * qty

            if bid_total >= base_to_sell:
                # we can sell all we need within this bid's total
                quote_bought += base_to_sell * price
                base_to_sell -= base_to_sell
                break
            elif base_to_sell > bid_total:
                # we are trying to buy more than this bid total, move on to next bid
                quote_bought += bid_total * price
                base_to_sell -= bid_total

        if base_to_sell > 0.0:
            print('Not enough order book info to calculate trade quantity estimate. Consider increasing the limit parameter.')
            print('base_to_sell: ', base_to_sell)

        return quote_bought

    @staticmethod
    def estimate_buy_order_result(order_book, input_qty):
        # TODO: truncate with step size here
        # use this if inversion for the trade is False
        # input_qty should be amount of the quote asset, the result from the previous trade
        # return the QTY base asset resulting from from buying against the order book

        # amount = total_base / price

        quote_to_sell = input_qty
        base_bought = 0.0

        for ask in order_book['asks']:
            price = float(ask[0])
            qty = float(ask[1])
            ask_total = price * qty

            if ask_total >= quote_to_sell:
                # we can buy all we need within this ask's total
                base_bought += quote_to_sell * (1.0 / price)
                quote_to_sell -= quote_to_sell
                break
            elif quote_to_sell > ask_total:
                # we are trying to buy more than this ask total, move on to next ask
                base_bought += ask_total * (1.0 / price)
                quote_to_sell -= ask_total

        if quote_to_sell > 0.0:
            print('Not enough order book info to calculate trade quantity estimate. Consider increasing the limit parameter.')
            print('quote_to_sell: ', quote_to_sell)

        return base_bought


    def get_trade_received_limit(self, order_book, input_qty, inversion):
        if inversion:
            result, best_ask, ask_price = self.estimate_sell_limit_result(order_book, input_qty)
            return result * (1.0 - self.trade_fee), best_ask, ask_price
        result, best_bid, bid_price = self.estimate_buy_limit_result(order_book, input_qty)
        return result * (1.0 - self.trade_fee), best_bid, bid_price

    @staticmethod
    def estimate_sell_limit_result(order_book, input_qty):
        base_to_sell = input_qty
        best_ask = order_book['asks'][0]
        ask_price = float(best_ask[0])

        return base_to_sell * ask_price, best_ask, ask_price

    @staticmethod
    def estimate_buy_limit_result(order_book, input_qty):
        quote_to_sell = input_qty
        best_bid = order_book['bids'][0]
        bid_price = float(best_bid[0])

        return quote_to_sell / bid_price, best_bid, bid_price

    def place_arbitrage_trade(self):
        pass
        return

    @staticmethod
    def _request_exception(request, exception):
        print('Error executing HTTP GET request')
        print("Problem: {}: {}".format(request.url, exception))
        exit(1)

    @staticmethod
    def truncate(qty, step_size):
        return float(str(float(qty) - (float(qty) % float(step_size)))[:8])

    def get_bids_and_asks(self, n=200, symbol='ETHUSDT'):
        # get the last n trades and sort them into bids and asks
        trades = self.client.get_recent_trades(symbol=symbol, limit=n)
        bids = []
        asks = []
        for trade in trades:
            if trade['isBuyerMaker']:
                bids.append(trade)
            else:
                asks.append(trade)
        return bids, asks

    @staticmethod
    def est_time_to_fill_order(trade_list, now=int(time.time() * 1000)):
        # calculate frequency
        time_delta = now - trade_list[-11]['time']  # in ms
        # print(time_delta)
        frequency = (float(len(trade_list[-11:-1])) / time_delta)  # trades / ms
        # print(frequency)
        est_time = 1.0 / frequency
        # print(est_time) # in ms
        return est_time

    def trade(self, asset_a_qty):
        print('ayyy lmao')
        # run this periodically

        #debug_time = time.time()
        #print('debug_time: ', debug_time)
        cycle_now = int(time.time()*1000)
        print(datetime.now().strftime('%H:%M:%S'))

        # TODO: subtract trading fees
        bids_a, asks_a = self.get_bids_and_asks(n=200, symbol='BNBUSDT') # invert
        bids_b, asks_b = self.get_bids_and_asks(n=200, symbol='BCCBNB') # invert
        bids_c, asks_c = self.get_bids_and_asks(n=200, symbol='BCCUSDT') # don't invert

        # format the data for a standard direction trade
        implicit_result = 1.0/float(bids_a[-1]['price']) * 1.0/float(asks_b[-1]['price']) * float(asks_c[-1]['price']) * asset_a_qty
        a_bid_t_est = int(self.est_time_to_fill_order(bids_a, now=cycle_now))
        c_ask_t_est =  int(self.est_time_to_fill_order(asks_c, now=cycle_now))
        a_bid_qty = float(bids_a[-1]['qty'])
        c_ask_qty = float(asks_c[-1]['qty'])
        print('implied standard trade profit: $', implicit_result - asset_a_qty)
        print('estimated time to fill order a: ', a_bid_t_est)
        print('estimated time to fill order c: ', c_ask_t_est)
        print('estimated time to fill orders total: ', a_bid_t_est + c_ask_t_est)

        # format the data for a reverse direction trade
        implicit_result_other = float(bids_c[-1]['price']) * 1.0/float(bids_b[-1]['price']) * 1.0/float(asks_a[-1]['price']) * asset_a_qty
        c_bid_t_est = int(self.est_time_to_fill_order(bids_c, now=cycle_now))
        a_ask_t_est = int(self.est_time_to_fill_order(asks_a, now=cycle_now))
        c_bid_qty = float(bids_c[-1]['qty'])
        a_ask_qty = float(asks_a[-1]['qty'])
        print('implied reverse trade profit:  $', implicit_result_other - asset_a_qty)
        print('estimated time to fill order c: ', c_bid_t_est)
        print('estimated time to fill order a: ', a_ask_t_est)
        print('estimated time to fill orders total: ', c_bid_t_est + a_ask_t_est)
        print('(time estimates are in milliseconds)')
        print()

        # this can be written to a csv file
        out_string = ', '.join([str(int(time.time())),
                                str(implicit_result - asset_a_qty),
                                str(a_bid_t_est),
                                str(c_ask_t_est),
                                str(a_bid_t_est + c_ask_t_est),
                                str(a_bid_qty),
                                str(c_ask_qty),
                                str(implicit_result_other - asset_a_qty),
                                str(c_bid_t_est),
                                str(a_ask_t_est),
                                str(c_bid_t_est + a_ask_t_est),
                                str(c_bid_qty),
                                str(a_ask_qty),])

        print()
