import baostock as bs
import pandas as pd

# 直接复制你修好的 get_stock_kline 函数粘贴在这里
def get_stock_kline(stock_code, start_date):
    if stock_code.startswith(('600', '601', '603', '605')):
        bs_code = f"sh.{stock_code}"
    elif stock_code.startswith(('000', '001', '300')):
        bs_code = f"sz.{stock_code}"
    else:
        return pd.DataFrame()

    fields = "date,open,high,low,close,preclose,volume,amount,turn,pctChg"
    rs = bs.query_history_k_data_plus(
        code=bs_code,
        fields=fields,
        start_date=start_date,
        end_date="",
        frequency="d",
        adjustflag="2"
    )
    print(f">>> 接口返回 error_code={rs.error_code}, msg={rs.error_msg}")

    data_list = []
    while (rs.error_code == '0') & rs.next():
        data_list.append(rs.get_row_data())

    if not data_list:
        return pd.DataFrame()

    df = pd.DataFrame(data_list, columns=[
        'trade_date', 'open', 'high', 'low', 'close', 'preclose',
        'volume', 'amount', 'turnover', 'pct_chg'
    ])
    df["change_amount"] = df["close"].astype(float) - df["preclose"].astype(float)
    return df

# 测试
if __name__ == "__main__":
    lg = bs.login()
    print(lg.error_msg)
    df = get_stock_kline("600000", "2020-01-01")
    print(f"行数:{len(df)}")
    print(df.head())
    bs.logout()
