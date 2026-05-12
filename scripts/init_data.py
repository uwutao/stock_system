import akshare as ak
import pandas as pd
from sqlalchemy import create_engine
import time

# 数据库连接配置
DB_URI = 'postgresql://postgres:stock123456@localhost:5432/stock_data'
engine = create_engine(DB_URI)

def get_stock_list():
    print("正在获取A股股票列表...")
    return ak.stock_info_a_code_name()

def save_daily_kline(stock_code, stock_name, start_date="20200101"):
    try:
        # 最新版akshare API参数不变
        df = ak.stock_zh_a_hist(
            symbol=stock_code, 
            period="daily", 
            start_date=start_date, 
            adjust="qfq"
        )
        
        if df.empty:
            return

        # 数据清洗和重命名（完全兼容最新版）
        df.rename(columns={
            '日期': 'trade_date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '振幅': 'amplitude', '涨跌幅': 'pct_chg',
            '涨跌额': 'change_amount', '换手率': 'turnover'
        }, inplace=True)
        
        df['stock_code'] = stock_code
        df['stock_name'] = stock_name
        
        # 批量存入数据库
        df.to_sql(
            'daily_kline', 
            engine, 
            if_exists='append', 
            index=False, 
            method='multi',
            chunksize=1000
        )
        print(f"✅ 成功入库: {stock_code} {stock_name}")

    except Exception as e:
        print(f"❌ 处理失败 {stock_code}: {str(e)}")

if __name__ == "__main__":
    # 1. 获取所有A股股票
    stock_df = get_stock_list()
    print(f"共获取到 {len(stock_df)} 只A股股票")
    
    # 2. 先测试前20只，确保没问题再跑全部
    test_stocks = stock_df.head(20)
    
    print(f"\n开始入库测试数据，共 {len(test_stocks)} 只股票...\n")
    
    # 3. 循环入库
    success_count = 0
    for index, row in test_stocks.iterrows():
        code = row['code']
        name = row['name']
        save_daily_kline(code, name)
        success_count += 1
        time.sleep(0.3)  # 防止请求过快被限流
    
    print(f"\n🎉 测试完成！成功入库 {success_count} 只股票数据")
    print("现在你可以修改脚本中的 test_stocks = stock_df 来入库全部A股数据")
