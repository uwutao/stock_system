import baostock as bs
import pandas as pd
import time
import random
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type,wait_exponential
from database.db import execute_sql, init_database, engine
from config.settings import COLLECTOR
import psycopg2

# 全局日志配置
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_all_stocks():
    """获取所有A股股票代码和名称（你原始的稳定逻辑）"""
    try:
        time.sleep(random.uniform(0.5, 1.5))
        rs = bs.query_stock_basic()
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        stock_df = pd.DataFrame(data_list).iloc[:, :2]
        stock_df.columns = ['code', 'name']
        stock_df['code'] = stock_df['code'].str.replace(r'^sh\.|^sz\.', '', regex=True)

        # 你原始的过滤规则（完全保留）
        def is_tradable(code, name):
            if 'ST' in name or '*ST' in name or '退' in name:
                return False
            # 排除指数
            if '指数' in name:
                return False
            return code.startswith(('600','601','603','605','000','001','300'))

        filtered_df = stock_df[stock_df.apply(lambda x: is_tradable(x['code'], x['name']), axis=1)]
        print(f"✅ 总股票数：{len(stock_df)} | 可交易：{len(filtered_df)}")
        return filtered_df
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        time.sleep(1)
        return pd.DataFrame()

@retry(
    stop=stop_after_attempt(COLLECTOR['max_retries']),
    wait=wait_exponential(multiplier=1, min=COLLECTOR['min_delay'], max=COLLECTOR['max_delay']),
    retry=retry_if_exception_type((Exception,))
)
def get_stock_kline(stock_code, start_date=COLLECTOR['start_date']):
    """获取k线数据，修复baostock change字段移除问题"""
    if stock_code.startswith(('600', '601', '603', '605')):
        bs_code = f"sh.{stock_code}"
    elif stock_code.startswith(('000', '001', '300')):
        bs_code = f"sz.{stock_code}"
    else:
        return pd.DataFrame()

    # 移除失效 change 字段
    fields = "date,open,high,low,close,preclose,volume,amount,turn,pctChg"
    rs = bs.query_history_k_data_plus(
        code=bs_code,
        fields=fields,
        start_date=start_date,
        end_date="",
        frequency="d",
        adjustflag="2"
    )

    data_list = []
    while (rs.error_code == '0') & rs.next():
        data_list.append(rs.get_row_data())

    if not data_list:
        return pd.DataFrame()

    df = pd.DataFrame(data_list, columns=[
        'trade_date', 'open', 'high', 'low', 'close', 'preclose',
        'volume', 'amount', 'turnover', 'pct_chg'
    ])
    # 本地计算涨跌额，对应原来 change
    df["change_amount"] = df["close"].astype(float) - df["preclose"].astype(float)
    return df


def save_daily_kline(stock_code, stock_name):
    """保存数据，完全适配旧表结构，不丢任何字段"""
    try:
        df = get_stock_kline(stock_code)
        if df.empty:
            logger.warning(f"{stock_code} {stock_name} 无K线数据，跳过")
            return False
        # 补充股票代码/名称，对齐旧表
        df['stock_code'] = stock_code
        df['stock_name'] = stock_name

        chunk_size = 200
        total_rows = len(df)
        logger.info(f"开始入库 {stock_code} {stock_name}，总行数 {total_rows}，分{ (total_rows + chunk_size -1) // chunk_size }批")

        for i in range(0, total_rows, chunk_size):
            batch_df = df.iloc[i:i+chunk_size]
            batch_df.to_sql(
                'daily_kline',
                engine,
                if_exists='append',
                index=False,
                # ========== 删掉 method="multi" 这一行！ ==========
                chunksize=chunk_size
            )
            logger.info(f"  - {stock_code} 批次 {i//chunk_size+1} 完成，{len(batch_df)}行")

        logger.info(f"✅ {stock_code} {stock_name} 全部入库完成，共 {total_rows} 行")
        return True
    except Exception as e:
        logger.error(f"❌ 处理失败 {stock_code} {stock_name}: {str(e)}")
        return False


# ---------------------- 主采集逻辑：优化进度条，快速跳过失败股票 ----------------------
def collect_all_stocks():
    """批量采集所有个股日线数据"""
    # 初始化数据库（自动建表）
    init_database()
    
    # 获取个股列表
    stock_df = get_all_stocks()
    stock_df = stock_df[ stock_df['code'].str.match(r'^(600|601|603|605|000|001|300)\d{3}$') ]
    if stock_df.empty:
        print("❌ 无个股数据，程序退出")
        return
    
    # 获取已采集过的股票，避免重复采集
    with engine.connect() as conn:
        try:
            collected = pd.read_sql("SELECT DISTINCT code FROM daily_kline", conn)['code'].tolist()
        except:
            collected = []
    
    # 过滤未采集的股票
    remaining = stock_df[~stock_df['code'].isin(collected)].reset_index(drop=True)
    print(f"已采集：{len(collected)} | 待采集：{len(remaining)}")
    
    # 批量采集（进度条+快速跳过失败）
    success = 0
    failed = 0
    for _, row in tqdm(remaining.iterrows(), total=len(remaining), desc="采集进度"):
        code, name = row['code'], row['name']
        if save_daily_kline(code, name):
            success += 1
        else:
            failed += 1
    
    print(f"\n采集完成！成功：{success} | 失败：{failed}")