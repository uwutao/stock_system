"""
文件：analysis/longterm_stats.py
功能：单只股票长周期统计摘要计算（约3年）
职责：接收 stock_code，内部通过 repo 读库计算，返回结构化统计字典
原则：原始K线只用于程序数学运算，绝不直接丢给大模型，规避token上限
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from repository.kline_repo import get_history_bars, get_basic_info


def _to_none_if_nan(val):
    """把 np.nan / pd.NA / None 全部转为 Python 原生 None，保证 JSON 可序列化"""
    if val is None:
        return None
    if pd.isna(val):
        return None
    return float(val)


def calc_stock_longterm_stats(stock_code: str):
    """
    长周期指标计算：读取最多750个交易日K线(≈3年)，pandas 做定量统计
    :param stock_code: 6位股票代码
    :return: 结构化统计字典；历史不足120天返回 None
    输出字段：
      价格：近3年总涨跌幅、价格分位、最大回撤、区间高低点
      量能：250日平均换手率
      估值：PE/PB 当前值 + 历史分位
    """
    df = get_history_bars(stock_code, limit=750)
    if df.shape[0] < 120:
        return None

    basic = get_basic_info(stock_code)

    start_price = df["close"].iloc[0]
    latest_price = df["close"].iloc[-1]
    max_price_3y = df["high"].max()
    min_price_3y = df["low"].min()

    total_return_3y = ((latest_price / start_price) - 1) * 100 if start_price else None
    price_percentile_3y = (
        (latest_price - min_price_3y) / (max_price_3y - min_price_3y) * 100
        if max_price_3y > min_price_3y else 50.0
    )

    cum_max = df["close"].cummax()
    drawdown = (df["close"] / cum_max - 1) * 100
    max_drawdown_3y = drawdown.min()

    turnover_mean_250 = df["turnover"].tail(250).mean()

    # 估值分位：当前 PE/PB 在历史样本中的分位
    pe_series = df["peTTM"].dropna() if "peTTM" in df.columns else pd.Series(dtype="float64")
    pb_series = df["pbMRQ"].dropna() if "pbMRQ" in df.columns else pd.Series(dtype="float64")

    pe_latest = df["peTTM"].iloc[-1] if "peTTM" in df.columns else None
    pb_latest = df["pbMRQ"].iloc[-1] if "pbMRQ" in df.columns else None

    pe_pct = None
    pb_pct = None
    if len(pe_series) > 30 and pe_latest is not None and not pd.isna(pe_latest):
        pe_pct = round((pe_series < pe_latest).sum() / len(pe_series) * 100, 1)
    if len(pb_series) > 30 and pb_latest is not None and not pd.isna(pb_latest):
        pb_pct = round((pb_series < pb_latest).sum() / len(pb_series) * 100, 1)

    stats = {
        "stock_code": stock_code,
        "stock_name": basic["stock_name"] if basic else "",
        "industry": basic["industry"] if basic else "未知",
        "data_days": len(df),
        "latest_price": _to_none_if_nan(latest_price),
        "total_return_3y_pct": _to_none_if_nan(round(total_return_3y, 2) if total_return_3y is not None else None),
        "price_3y_percentile": _to_none_if_nan(round(price_percentile_3y, 2)),
        "max_price_3y": _to_none_if_nan(max_price_3y),
        "min_price_3y": _to_none_if_nan(min_price_3y),
        "max_drawdown_3y_pct": _to_none_if_nan(round(max_drawdown_3y, 2)),
        "turnover_mean_250": _to_none_if_nan(round(turnover_mean_250, 2)),
        "pe_latest": _to_none_if_nan(pe_latest),
        "pe_3y_percentile": pe_pct,
        "pb_latest": _to_none_if_nan(pb_latest),
        "pb_3y_percentile": pb_pct,
    }
    return stats