"""
文件：repository/kline_repo.py
功能：K线 / 股票基础信息 查询的统一入口
职责：所有对 daily_kline / stock_basic 的 SELECT 集中在这里
原则：只做数据读取，不做业务计算，不调 LLM，不做写入
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from sqlalchemy import text
from database.db_bak import engine


def get_latest_bars(exclude_st: bool = True) -> pd.DataFrame:
    """
    获取每只股票最新一条日线 + 行业
    :param exclude_st: 是否排除 ST 股票（NULL 视为非 ST）
    :return: DataFrame，字段 stock_code/stock_name/trade_date/close/volume/turnover/pct_chg/industry
    """
    # ✅ 修复：原 isST <> '1' 会过滤掉 NULL 行，这里显式放行 NULL
    is_st_where = "AND (d.isST IS NULL OR d.isST <> '1')" if exclude_st else ""
    sql = text(f"""
    SELECT DISTINCT ON(d.stock_code)
        d.stock_code, d.stock_name, d.trade_date,
        d.close::double precision AS close,
        d.volume::double precision AS volume,
        d.turnover::double precision AS turnover,
        d.pct_chg::double precision AS pct_chg,
        b.industry
    FROM daily_kline d
    LEFT JOIN stock_basic b ON d.stock_code = b.stock_code
    WHERE 1=1 {is_st_where}
    ORDER BY d.stock_code, d.trade_date DESC;
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_history_bars(stock_code: str, limit: int = 750) -> pd.DataFrame:
    """
    获取单只股票历史日线（时间升序）
    :param stock_code: 6位数字代码
    :param limit: 最多返回条数，默认750（约3年）
    :return: DataFrame，字段 trade_date/open/high/low/close/volume/turnover/pct_chg/peTTM/pbMRQ
    """
    sql = text("""
        SELECT trade_date, open, high, low, close, volume, turnover, pct_chg, peTTM, pbMRQ
        FROM daily_kline
        WHERE stock_code = :sc
        ORDER BY trade_date ASC
        LIMIT :lim
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"sc": stock_code, "lim": limit}).mappings().all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)


def get_batch_history_bars(code_list: list) -> pd.DataFrame:
    """
    批量获取一批股票全部历史日线（用于多周期趋势计算）
    :param code_list: 股票代码列表
    :return: DataFrame，字段 stock_code/trade_date/close
    """
    if not code_list:
        return pd.DataFrame()
    sql = text("""
        SELECT stock_code, trade_date, close
        FROM daily_kline
        WHERE stock_code IN :code_arr
        ORDER BY stock_code, trade_date ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"code_arr": tuple(code_list)}).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["close"] = df["close"].astype(float)
    return df


def get_basic_info(stock_code: str):
    """
    获取单只股票基础信息（名称、行业）
    :return: dict 或 None
    """
    sql = text("SELECT stock_name, industry FROM stock_basic WHERE stock_code = :sc")
    with engine.connect() as conn:
        row = conn.execute(sql, {"sc": stock_code}).mappings().first()
    return dict(row) if row else None


def get_single_stock_info(stock_code: str):
    """
    获取单只股票最新一条日线 + 行业 + pe/pb（旧接口兼容）
    :return: dict 或 None
    """
    sql = text("""
    SELECT d.stock_code, d.stock_name, d.close, d.pct_chg, d.turnover, d.peTTM, d.pbMRQ, b.industry
    FROM daily_kline d
    LEFT JOIN stock_basic b ON d.stock_code = b.stock_code
    WHERE d.stock_code = :sc
    ORDER BY d.trade_date DESC LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"sc": stock_code}).mappings().first()
    return dict(row) if row else None