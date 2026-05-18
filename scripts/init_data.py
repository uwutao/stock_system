import baostock as bs
import pandas as pd
from sqlalchemy import create_engine
import time

# 数据库连接配置
DB_URI = 'postgresql://postgres:stock123456@localhost:5432/stock_data'
engine = create_engine(DB_URI)

def get_stock_list():
    """通过Baostock获取所有A股股票列表"""
    print("正在获取A股股票列表...")
    # 登录
    lg = bs.login()
    if lg.error_code != '0':
        raise Exception(f"Baostock登录失败: {lg.error_msg}")
    
    try:
        # 获取股票基本信息
        rs = bs.query_stock_basic(code_name="", exchange="", field="code,code_name")
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        stock_df = pd.DataFrame(data_list, columns=['code', 'name'])
        
        # 去掉sh./sz.前缀
        stock_df['code'] = stock_df['code'].str.replace('sh.', '').str.replace('sz.', '')
        return stock_df
    finally:
        # 登出
        bs.logout()

def get_stock_kline(stock_code, start_date="20200101"):
    """获取单只股票K线数据"""
    lg = bs.login()
    if lg.error_code != '0':
        raise Exception(f"Baostock登录失败: {lg.error_msg}")
    
    try:
        # 处理代码前缀
        if stock_code.startswith(('600', '601', '603', '605')):
            bs_code = f"sh.{stock_code}"
        elif stock_code.startswith(('000', '001', '300')):
            bs_code = f"sz.{stock_code}"
        else:
            return pd.DataFrame()
        
        # 获取K线数据
        fields = "date,open,high,low,close,preclose,volume,amount,turnover,change,pctChg"
        rs = bs.query_history_k_data_plus(
            code=bs_code,
            fields=fields,
            start_date=start_date,
            end_date="",
            frequency="d",
            adjustflag="2"
        )
        
        # 转换为DataFrame
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        df = pd.DataFrame(data_list, columns=rs.fields)
        
        # 类型转换
        numeric_fields = ['open', 'high', 'low', 'close', 'preclose', 'volume', 
                         'amount', 'turnover', 'change', 'pctChg']
        for field in numeric_fields:
            df[field] = pd.to_numeric(df[field], errors='coerce')
        
        # 计算振幅
        df['amplitude'] = (df['high'] - df['low']) / df['preclose'] * 100
        df['amplitude'] = df['amplitude'].round(2)
        
        return df
    finally:
        bs.logout()

def save_daily_kline(stock_code, stock_name, start_date="20200101"):
    try:
        df = get_stock_kline(stock_code, start_date)
        
        if df.empty:
            print(f"⚠️  无数据: {stock_code} {stock_name}")
            return

        # 数据清洗和重命名
        df.rename(columns={
            'date': 'trade_date',
            'pctChg': 'pct_chg',
            'change': 'change_amount'
        }, inplace=True)
        
        # 保留字段
        keep_fields = ['trade_date', 'open', 'close', 'high', 'low', 'volume', 
                      'amount', 'amplitude', 'pct_chg', 'change_amount', 'turnover']
        df = df[keep_fields]
        
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
    # 1. 安装依赖
    import subprocess
    subprocess.run(["pip", "install", "baostock", "sqlalchemy", "psycopg2-binary", 
                   "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
    
    # 2. 获取所有A股股票
    stock_df = get_stock_list()
    print(f"共获取到 {len(stock_df)} 只A股股票")
    
    # 3. 先测试前20只，确保没问题再跑全部
    test_stocks = stock_df.head(20)
    
    print(f"\n开始入库测试数据，共 {len(test_stocks)} 只股票...\n")
    
    # 4. 循环入库
    success_count = 0
    for index, row in test_stocks.iterrows():
        code = row['code']
        name = row['name']
        save_daily_kline(code, name)
        success_count += 1
        time.sleep(0.3)  # 防止请求过快被限流
    
    print(f"\n🎉 测试完成！成功入库 {success_count} 只股票数据")
    print("现在你可以修改脚本中的 test_stocks = stock_df 来入库全部A股数据")