import baostock as bs
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

# 重试机制（适配Baostock异常）
@retry(
    stop=stop_after_attempt(COLLECTOR['max_retries']),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type((Exception,))  # Baostock异常统一捕获
)
def get_stock_kline(stock_code, start_date=COLLECTOR['start_date']):
    """
    通过Baostock获取股票K线数据
    :param stock_code: 纯数字代码（如600000）
    :param start_date: 开始日期（YYYYMMDD）
    :return: DataFrame
    """
    # 1. 登录Baostock
    lg = bs.login()
    if lg.error_code != '0':
        raise Exception(f"Baostock登录失败: {lg.error_msg}")
    
    try:
        # 2. 处理股票代码前缀
        if stock_code.startswith(('600', '601', '603', '605')):
            bs_code = f"sh.{stock_code}"
        elif stock_code.startswith(('000', '001', '300')):
            bs_code = f"sz.{stock_code}"
        else:
            return pd.DataFrame()  # 非目标板块直接返回空
        
        # 3. 获取K线数据（指定需要的字段）
        fields = "date,open,high,low,close,preclose,volume,amount,turnover,change,pctChg"
        rs = bs.query_history_k_data_plus(
            code=bs_code,
            fields=fields,
            start_date=start_date,
            end_date="",  # 空表示取最新
            frequency="d",  # 日线
            adjustflag="2"  # 前复权（对应akshare的qfq）
        )
        
        # 4. 转换为DataFrame
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        df = pd.DataFrame(data_list, columns=rs.fields)
        
        # 5. 数据类型转换
        numeric_fields = ['open', 'high', 'low', 'close', 'preclose', 'volume', 
                         'amount', 'turnover', 'change', 'pctChg']
        for field in numeric_fields:
            df[field] = pd.to_numeric(df[field], errors='coerce')
        
        # 6. 计算振幅 (high-low)/preclose * 100
        df['amplitude'] = (df['high'] - df['low']) / df['preclose'] * 100
        df['amplitude'] = df['amplitude'].round(2)
        
        return df
    
    finally:
        # 确保登出
        bs.logout()

def get_collected_stocks():
    """获取已经采集过的股票列表"""
    result = execute_sql("SELECT DISTINCT stock_code FROM daily_kline")
    return {row[0] for row in result.fetchall()}

def save_daily_kline(stock_code, stock_name):
    try:
        df = get_stock_kline(stock_code)
        
        if df.empty:
            return False

        # 数据清洗和重命名（对齐原有字段名）
        df.rename(columns={
            'date': 'trade_date',
            'pctChg': 'pct_chg',
            'change': 'change_amount',
            'turnover': 'turnover'
        }, inplace=True)
        
        # 保留需要的字段
        keep_fields = ['trade_date', 'open', 'close', 'high', 'low', 'volume', 
                      'amount', 'amplitude', 'pct_chg', 'change_amount', 'turnover']
        df = df[keep_fields]
        
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
    """获取所有A股股票代码和名称（通过Baostock）"""
    try:
        time.sleep(random.uniform(0.5, 1.5))
        
        # 1. 登录Baostock
        lg = bs.login()
        if lg.error_code != '0':
            raise Exception(f"Baostock登录失败: {lg.error_msg}")
        
        # 2. 获取所有A股基本信息
        rs = bs.query_stock_basic(code_name="", exchange="", field="code,code_name")
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        stock_df = pd.DataFrame(data_list, columns=['code', 'name'])
        
        # 3. 去掉Baostock前缀（sh./sz.）
        stock_df['code'] = stock_df['code'].str.replace('sh.', '').str.replace('sz.', '')
        
        # 4. 原有过滤规则保留
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
                
            # 其他全部排除
            return False
        
        # 应用过滤
        filtered_df = stock_df[stock_df.apply(lambda x: is_tradable(x['code'], x['name']), axis=1)]
        
        print(f"✅ 总股票数：{len(stock_df)}")
        print(f"✅ 可交易股票数：{len(filtered_df)}")
        print(f"❌ 已排除：{len(stock_df) - len(filtered_df)} 只股票")
        
        # 登出
        bs.logout()
        
        return filtered_df
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        time.sleep(3)
        return get_all_stocks()