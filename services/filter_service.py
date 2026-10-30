"""
文件：services/filter_service.py
功能：筛选核心逻辑
职责：查库 → 算趋势 → 加权 → 返回候选列表
原则：✅ 不调 LLM，✅ 不写库。这样才能单测，也方便被不同上层复用
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from config.settings import TREND_CONFIG
from repository.kline_repo import get_latest_bars, get_batch_history_bars
from analysis.trend import calc_multi_period_trend_from_df, label_to_emoji


def calc_single_day_score(row) -> float:
    """
    单日量价快照分数（0~100），作为辅助信号
    仅在 TREND_CONFIG['weight_single_day'] > 0 时才影响总分
    """
    score = 0
    pct_chg = row["pct_chg"]
    volume = row["volume"]
    turnover = row["turnover"]
    if pct_chg > 0:
        score += 20
        if pct_chg > 2:
            score += 10
        if pct_chg > 4:
            score += 10
    elif pct_chg < -2:
        score -= 10
    if volume > 0:
        score += 10
    if 1 < turnover < 8:
        score += 15
    if turnover > 15:
        score -= 10
    return max(0, min(score, 100))


def calc_total_weight_score(r, cfg: dict) -> float:
    """
    加权合成综合趋势总分（0~100）
    权重：短周期25 + 中周期35 + 长周期40，单日量价由配置决定
    数据不足的周期权重自动置0（不拉低总分）
    """
    w_s = cfg["weight_short"]
    w_m = cfg["weight_mid"]
    w_l = cfg["weight_long"]
    w_day = cfg["weight_single_day"]

    real_w_short = w_s if r["trend_short_label"] != "no_data" else 0
    real_w_mid = w_m if r["trend_mid_label"] != "no_data" else 0
    real_w_long = w_l if r["trend_long_label"] != "no_data" else 0

    w_sum = real_w_short + real_w_mid + real_w_long + w_day
    if w_sum <= 0:
        return 0.0

    total = (
        r["trend_short_score"] * real_w_short
        + r["trend_mid_score"] * real_w_mid
        + r["trend_long_score"] * real_w_long
        + r["single_day_score"] * w_day
    ) / w_sum
    return round(total, 1)


def filter_candidates(min_price: float, max_price: float, max_count: int = 20) -> pd.DataFrame:
    """
    核心筛选：不调 LLM，不写库，纯计算
    步骤：
      1. 拿每只股票最新一条日线（已排除ST）
      2. 价格区间过滤
      3. 批量拉历史 → 多周期趋势
      4. 加权合成 ai_total_score
      5. 排序取前 max_count
    :return: DataFrame，字段含 code/name/close/pct_chg/turnover/trend_*_text/ai_total_score
    """
    cfg = TREND_CONFIG

    # 1) 最新日线
    df_latest = get_latest_bars(exclude_st=True)
    if df_latest.empty:
        return pd.DataFrame()

    # 2) 价格过滤
    df_latest = df_latest[(df_latest["close"] >= min_price) & (df_latest["close"] <= max_price)]
    if df_latest.empty:
        return pd.DataFrame()

    # 3) 单日快照分
    df_latest["single_day_score"] = df_latest.apply(calc_single_day_score, axis=1)

    # 4) 批量历史 + 多周期趋势
    code_list = df_latest["stock_code"].tolist()
    df_raw = get_batch_history_bars(code_list)
    df_trend = calc_multi_period_trend_from_df(df_raw, cfg)
    if df_trend.empty:
        return pd.DataFrame()

    df_merge = pd.merge(df_latest, df_trend, on="stock_code", how="left")

    # 5) 加权综合分 + 排序截断
    df_merge["ai_total_score"] = df_merge.apply(lambda r: calc_total_weight_score(r, cfg), axis=1)
    df_merge = (
        df_merge[df_merge["ai_total_score"] > 0]
        .sort_values("ai_total_score", ascending=False)
        .head(max_count)
        .reset_index(drop=True)
    )

    # 6) 前端展示文本
    df_merge["trend_short_text"] = df_merge["trend_short_label"].apply(label_to_emoji)
    df_merge["trend_mid_text"] = df_merge["trend_mid_label"].apply(label_to_emoji)
    df_merge["trend_long_text"] = df_merge["trend_long_label"].apply(label_to_emoji)

    df_merge.rename(columns={"stock_code": "code", "stock_name": "name"}, inplace=True)
    return df_merge