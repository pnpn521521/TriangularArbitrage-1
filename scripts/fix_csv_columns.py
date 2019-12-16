import pandas as pd

df = pd.read_csv('BCCUSDT_orig.csv', header=None, names=['b','a','E','M','m','q','p','s','t','e','T'])

fixed_columns = ['E', 'M', 'T', 'a', 'b', 'e', 'm', 'p', 'q', 's', 't']

fixed_df = df[fixed_columns]

print(fixed_df.head())

fixed_df.to_csv('BCCUSDT_fixed.csv', index=False)

