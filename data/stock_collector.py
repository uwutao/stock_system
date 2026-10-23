import baostock as bs
import pandas as pd
import time
import random
from datetime import date, timedelta
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from database.db import execute_sql, init_database, engine
from config.settings import COLLECTOR
import psycopg2
from sqlalchemy import text
import socket

# 全局日志配置
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局保存登录状态
bs_session = None

def baostock_relogin():
    """断开旧连接，重新登录baostock，用于broken pipe后重置socket"""
    global bs_session
    try:
        bs.logout()
    except Exception:
        pass
    lg = bs.login()
    if lg.error_code != '0':
        logger.error(f"baostock重登录失败: {lg.error_msg}")
        return False
    logger.info("🔄 baostock 会话重登录成功")
    bs_session = lg
    return True


def clean_empty_to_none(val):
    """baostock空字符串转为None，适配PG NULL"""
    if isinstance(val, str):
        s = val.strip()
        if s == "":
            return None
    return val


def safe_float(x):
    """None安全浮点转换"""
    if x is None:
        return None
    return float(x)


def get_stock_last_trade_date(stock_code: str):
    """
    查询数据库中该股票的最大trade_date
    :return: None(库无数据) / date对象
    """
    sql = text("SELECT MAX(trade_date) as max_dt FROM daily_kline WHERE stock_code = :sc")
    with engine.connect() as conn:
        res = conn.execute(sql, {"sc": stock_code})
        row = res.fetchone()
        if row is None or row.max_dt is None:
            return None
        return row.max_dt


def get_all_stocks():
    """获取所有A股股票代码和名称，读取type字段过滤指数/基金/债券"""
    try:
        time.sleep(random.uniform(0.5, 1.5))
        rs = bs.query_stock_basic()
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        # baostock新版：6列 code,name,ipoDate,outDate,type,status
        stock_df = pd.DataFrame(data_list, columns=['code', 'name', 'ipoDate', 'outDate', 'type', 'status'])
        stock_df['code'] = stock_df['code'].str.replace(r'^sh\.|^sz\.', '', regex=True)

        def is_tradable(row):
            code = row["code"]
            name = row["name"]
            typ = row["type"]
            # type == "1" = A股股票；2指数、3基金、4债券全部过滤
            if typ != "1":
                return False
            if 'ST' in name or '*ST' in name or '退' in name:
                return False
            return code.startswith(('600', '601', '603', '605', '000', '001', '300'))

        filtered_df = stock_df[stock_df.apply(is_tradable, axis=1)]
        print(f"✅ 总标的数：{len(stock_df)} | 可交易A股：{len(filtered_df)}")
        return filtered_df
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        time.sleep(1)
        return pd.DataFrame()


@retry(
    stop=stop_after_attempt(COLLECTOR['max_retries']),
    wait=wait_exponential(multiplier=1, min=COLLECTOR['min_delay'], max=COLLECTOR['max_delay']),
    retry=retry_if_exception_type((socket.error, OSError, Exception))
)
def get_stock_kline(stock_code, start_date):
    """
    获取k线数据，支持动态传入start_date，用于增量采集
    捕获socket broken pipe异常
    :param stock_code: 纯数字代码
    :param start_date: str 'YYYY‑MM‑DD'
    :return: DataFrame
    """
    if stock_code.startswith(('600', '601', '603', '605')):
        bs_code = f"sh.{stock_code}"
    elif stock_code.startswith(('000', '001', '300')):
        bs_code = f"sz.{stock_code}"
    else:
        return pd.DataFrame()
    fields = "date,open,high,low,close,preclose,volume,amount,turn,pctChg"
    try:
        rs = bs.query_history_k_data_plus(
            code=bs_code,
            fields=fields,
            start_date=start_date,
            end_date="",
            frequency="d",
            adjustflag="2"
        )
    except OSError as e:
        # Broken pipe / bad fd 触发重登录
        logger.error(f"Socket异常 {e}, 需要重连baostock")
        baostock_relogin()
        raise
    data_list = []
    while (rs.error_code == '0') & rs.next():
        row = rs.get_row_data()
        cleaned_row = [clean_empty_to_none(item) for item in row]
        data_list.append(cleaned_row)
    if not data_list:
        return pd.DataFrame()
    df = pd.DataFrame(data_list, columns=[
        'trade_date', 'open', 'high', 'low', 'close', 'preclose',
        'volume', 'amount', 'turnover', 'pct_chg'
    ])
    # 安全浮点转换
    df['open'] = df['open'].apply(safe_float)
    df['high'] = df['high'].apply(safe_float)
    df['low'] = df['low'].apply(safe_float)
    df['close'] = df['close'].apply(safe_float)
    df['preclose'] = df['preclose'].apply(safe_float)
    df['volume'] = df['volume'].apply(safe_float)
    df['amount'] = df['amount'].apply(safe_float)
    df['turnover'] = df['turnover'].apply(safe_float)
    df['pct_chg'] = df['pct_chg'].apply(safe_float)
    # 涨跌额
    df["change_amount"] = df.apply(lambda r: safe_float(r["close"]) - safe_float(r["preclose"]), axis=1)
    # 振幅
    df["amplitude"] = df.apply(
        lambda r: ((r["high"] - r["low"]) / r["preclose"] * 100)
        if (r["high"] is not None and r["low"] is not None and r["preclose"] and r["preclose"] != 0)
        else None,
        axis=1
    )
    return df


def save_daily_kline(stock_code, stock_name):
    """
    增量采集：自动读取库中最新日期，接续拉取；ON CONFLICT DO NOTHING
    """
    try:
        last_dt = get_stock_last_trade_date(stock_code)
        today_str = date.today().strftime("%Y-%m-%d")
        if last_dt is not None:
            start_dt = (last_dt + timedelta(days=1)).strftime("%Y-%m-%d")
            logger.info(f"{stock_code} {stock_name} 库内最新:{last_dt}, 增量起始:{start_dt}")
            # 如果起始日期已经大于今天，不需要请求baostock，直接跳过，节省请求
            if start_dt > today_str:
                logger.info(f"{stock_code} {stock_name} 已采集至最新交易日，无需拉取数据")
                return True
        else:
            start_dt = COLLECTOR['start_date']
            logger.info(f"{stock_code} {stock_name} 库无历史，全量起始:{start_dt}")

        df = get_stock_kline(stock_code, start_date=start_dt)
        if df.empty:
            logger.warning(f"{stock_code} {stock_name} 查询返回空K线，无可用K线数据")
            return False

        df['stock_code'] = stock_code
        df['stock_name'] = stock_name
        chunk_size = 200
        total_rows = len(df)
        logger.info(f"开始入库 {stock_code} {stock_name}，本次拉取 {total_rows} 行，分{(total_rows + chunk_size -1)//chunk_size}批")

        insert_sql = text("""
            INSERT INTO daily_kline (
                stock_code, stock_name, trade_date, open, high, low, close, preclose,
                volume, amount, turnover, pct_chg, change_amount, amplitude
            )
            VALUES (:stock_code, :stock_name, :trade_date, :open, :high, :low, :close, :preclose,
                    :volume, :amount, :turnover, :pct_chg, :change_amount, :amplitude)
            ON CONFLICT (stock_code, trade_date) DO NOTHING;
        """)

        for i in range(0, total_rows, chunk_size):
            batch_df = df.iloc[i:i + chunk_size]
            records = batch_df.to_dict('records')
            with engine.connect() as conn:
                try:
                    result = conn.execute(insert_sql, records)
                    conn.commit()
                    inserted = result.rowcount
                    skip_cnt = len(batch_df) - inserted
                    logger.info(f"  - {stock_code} 批次 {i // chunk_size +1}：收到{len(batch_df)}行，实际入库{inserted}行，冲突跳过{skip_cnt}行")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"  ! {stock_code} 批次{i//chunk_size+1}写入异常: {str(e)}")
                    raise

        logger.info(f"✅ {stock_code} {stock_name} 本轮处理完成，拉取{total_rows}行")
        return True
    except Exception as e:
        logger.error(f"❌ 处理失败 {stock_code} {stock_name}: {str(e)}")
        return False


def collect_all_stocks():
    """单线程串行采集，增加定时刷新会话，更长sleep"""
    init_database()
    stock_df = get_all_stocks()
    if stock_df.empty:
        print("❌ 获取股票列表为空，程序退出")
        return

    stock_df = stock_df[stock_df['code'].str.match(r'^(600|601|603|605|000|001|300)\d{3}$')]
    if stock_df.empty:
        print("❌ 过滤后无个股数据，程序退出")
        return
    total_cnt = len(stock_df)
    print(f"待处理A股总数：{total_cnt}【单线程｜会话自动重连｜慢速限流】")

    success = 0
    failed = 0
    counter = 0
    refresh_interval = 80 # 每处理80只股票主动刷新一次baostock会话，预防长连接被踢

    for _, row in tqdm(stock_df.iterrows(), total=total_cnt, desc="采集进度"):
        code, name = row['code'], row['name']
        counter +=1
        # 定时刷新会话
        if counter % refresh_interval == 0:
            logger.info(f"每{refresh_interval}只股票，主动刷新baostock会话")
            baostock_relogin()

        ret = save_daily_kline(code, name)
        if ret:
            success +=1
        else:
            failed +=1
        # 拉长休眠时间：0.6 ~1.2秒，降低请求频率，缓解服务端断连
        time.sleep(random.uniform(0.6,1.2))

    print(f"\n采集一轮结束！成功:{success} | 失败:{failed}")


if __name__ == "__main__":
    lg = bs.login()
    if lg.error_code != '0':
        logger.error(f"baostock登录失败：{lg.error_msg}")
    else:
        collect_all_stocks()
    bs.logout()
    print("✅ 程序退出，baostock已登出")
