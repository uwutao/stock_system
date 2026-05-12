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
from requests.exceptions import RequestException

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

def get_all_stocks():
    """获取所有A股股票代码和名称"""
    try:
        # 原有的延迟和重试逻辑保留不变
        time.sleep(random.uniform(0.5, 1.5))
        stock_df = ak.stock_info_a_code_name()
        
        # ========== 只修改这里开始 ==========
        # 过滤规则：只保留上证主板、深证主板、创业板
        def is_tradable(code, name):
            # 排除ST股、*ST股和退市股
            if 'ST' in name or '*ST' in name or '退' in name:
                return False
                
            # 上证主板：600、601、603、605开头
            if code.startswith(('600', '601', '603', '605')):
                return True
                
            # 深证主板：000、001开头
            if code.startswith(('000', '001')):
                return True
                
            # 创业板：300开头
            if code.startswith('300'):
                return True
                
            # 其他全部排除（科创板688、北交所8/4开头等）
            return False
        
        # 应用过滤
        filtered_df = stock_df[stock_df.apply(lambda x: is_tradable(x['code'], x['name']), axis=1)]
        
        print(f"✅ 总股票数：{len(stock_df)}")
        print(f"✅ 可交易股票数：{len(filtered_df)}")
        print(f"❌ 已排除：{len(stock_df) - len(filtered_df)} 只股票")
        # ========== 只修改这里结束 ==========
        
        return filtered_df
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        time.sleep(3)
        return get_all_stocks()