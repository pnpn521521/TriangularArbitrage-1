import time
import PeriodicScheduler
from TriangularArbitrageModel import *

# run the triangular arbitrage system as a process
# TriangularArbitrageModel should be modified to configure if we are calculating live trade opportunities or placing those trades

model = TriangularArbitrageModel('USDT', 'BNB', 'BCC', 'LIMIT', 'MARKET', 'LIMIT')

print('Valid pair names:')
print(model.pair_a_valid_name, model.trade_a_inversion)
print(model.pair_b_valid_name, model.trade_b_inversion)
print(model.pair_c_valid_name, model.trade_c_inversion)
print()

# Simulate potential profit from the specified trade size
trade_amount = 400 # USDT
window = 60

profit_threshold = trade_amount + 2.00

model.update_account_info()
while True:
    # edit the async_update method of the model to change what this does
    model.async_update(asset_a_qty=trade_amount, profit_threshold=profit_threshold)
    time.sleep(1)
