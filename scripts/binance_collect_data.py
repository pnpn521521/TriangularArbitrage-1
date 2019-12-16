# Binance socket stream

# Collects live trade data from web socket API and stores each trade as a row into a csv file

import pprint
import os
import sys
import inspect
import time
import traceback

current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0,parent_dir)

from binance.client import Client
from binance.websockets import BinanceSocketManager

api_key = os.environ.get('STELLA_API_KEY')
secret_key = os.environ.get('STELLA_SECRET_KEY')

client = Client(api_key, secret_key)
bm = BinanceSocketManager(client)

trade_symbol = sys.argv[1]

out_file = trade_symbol+'.csv'


def process_message(msg):
    #os.system('cls')
    #instance = [str(value) for (key, value) in sorted(msg.items())]
    #for (key, value) in msg.items():
    #    print('key: ', key)
    #    print('value: ', value)
    #    print()
    #out_string = ', '.join(instance)
    out_string = ', '.join("=".join((k, str(v))) for k, v in sorted(msg.items()))
    print(out_string)
    #with open(out_file, 'a') as f:
    #    f.write(out_string)
    #    f.write('\n')
    #    f.close()

if __name__ == "__main__":
    try:
        conn_key = bm.start_trade_socket(trade_symbol, process_message)
        bm.start()
    except:
        print(sys.exc_info())
        print('Exception occurred... Exiting.')
        time.sleep(1)
        traceback.print_exc()
        exit(1)