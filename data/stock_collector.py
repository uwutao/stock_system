import akshare as ak
import pandas as pd
import time
import random
import logging
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
from database.db import execute_sql, init_database
from config.settings import COLLECTOR

# 配置日志
logger = logging.getLogger(__name__)

# 重试机制
@retry(
    stop=stop_after_attempt(COLLECTOR['max_retries']),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type((requests.exceptions.RequestException, ConnectionResetError))
)
def get_stock_kline(stock_code, start_date=COLLECTOR['start_date']):
    return ak.stock_zh_a_hist(
        symbol=stock_code, 
        period="daily", 
        start_date=start_date, 
        adjust="qfq"
    )

def get_collected_stocks():
    """获取已经采集过的股票列表"""
    result = execute_sql("SELECT DISTINCT stock_code FROM daily_kline")
    return {row[0] for row in result.fetchall()}

def save_daily_kline(stock_code, stock_name):
    try:
        df = get_stock_kline(stock_code)
        
        if df.empty:
            return False

        # 数据清洗和重命名
        df.rename(columns={
            '日期': 'trade_date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '振幅': 'amplitude', '涨跌幅': 'pct_chg',
            '涨跌额': 'change_amount', '换手率': 'turnover'
        }, inplace=True)
        
        df['stock_code'] = stock_code
        df['stock_name'] = stock_name
        
        # 批量存入数据库，冲突时忽略
        df.to_sql(
            'daily_kline', 
            execute_sql.bind, 
            if_exists='append', 
            index=False, 
            method='multi',
            chunksize=1000
        )
        return True

    except Exception as e:
        logger.error(f"处理失败 {stock_code} {stock_name}: {str(e)}")
        return False

def collect_all_stocks():
    """采集所有A股股票数据"""
    # 初始化数据库
    init_database()
    
    # 获取所有A股股票
    logger.info("正在获取A股股票列表...")
    stock_df = ak.stock_info_a_code_name()
    total_stocks = len(stock_df)
    logger.info(f"共获取到 {total_stocks} 只A股股票")
    
    # 获取已经采集过的股票
    collected_stocks = get_collected_stocks()
    logger.info(f"已经采集过 {len(collected_stocks)} 只股票")
    
    # 筛选出还未采集的股票
    remaining_stocks = stock_df[~stock_df['code'].isin(collected_stocks)]
    remaining_count = len(remaining_stocks)
    logger.info(f"剩余 {remaining_count} 只股票待采集")
    
    if remaining_count == 0:
        logger.info("🎉 所有股票数据已经采集完成！")
        return
    
    # 开始采集
    success_count = 0
    failed_count = 0
    
    pbar = tqdm(remaining_stocks.iterrows(), total=remaining_count, desc="采集进度")
    
    for index, row in pbar:
        code = row['code']
        name = row['name']
        
        if save_daily_kline(code, name):
            success_count += 1
        else:
            failed_count += 1
        
        # 更新进度条描述
        pbar.set_postfix({
            '成功': success_count,
            '失败': failed_count
        })
        
        # 随机延迟
        time.sleep(random.uniform(COLLECTOR['min_delay'], COLLECTOR['max_delay']))
    
    logger.info(f"✅ 采集完成！成功: {success_count}, 失败: {failed_count}")
    logger.info(f"总共已采集: {len(collected_stocks) + success_count} / {total_stocks} 只股票")
    
    if failed_count > 0:
        logger.info("💡 提示：失败的股票会在下次运行时自动重新采集")

if __name__ == "__main__":
    collect_all_stocks()