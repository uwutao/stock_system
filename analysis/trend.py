"""
文件：analysis/trend.py
功能：多周期趋势识别（纯函数模块）
职责：只做数学计算，不访问数据库，不调用 LLM
输入：收盘价 pd.Series / 批量历史 DataFrame
输出：趋势标签 + 分数
✅ 核心修复：用 log(close) 而非原始 close 计算斜率，修正高价股天然高分的问题
"""
import numpy as np
import pandas as pd


def calc_trend_single_series(close_ser: pd.Series, cfg: dict) -> dict:
    """
    计算单段收盘价序列的趋势（对数价格线性回归）
    为什么用 log(close)：
      - 原始价格斜率会被股价量级放大（茅台斜率天然大于8元股）
      - 对数斜率直接解读为"年化对数收益率"，可跨股票比较
    :param close_ser: 收盘价 Series，时间升序，建议前复权
    :param cfg: TREND_CONFIG 配置字典
    :return: dict {label, score, slope_all, slope_recent, max_dd, period_ret, annual_log_ret}
    label: up / sideways / down / no_data
    """
    n = len(close_ser)
    if n < 10:
        return {
            "label": "no_data", "score": 0,
            "slope_all": None, "slope_recent": None,
            "max_dd": None, "period_ret": None,
            "annual_log_ret": None,
        }

    # ✅ 关键修复：对数价格
    y = np.log(close_ser.values.astype(float))
    x = np.arange(n)
    slope_all, _ = np.polyfit(x, y, deg=1)

    half_n = max(n // 2, 10)
    y_recent = y[-half_n:]
    x_recent = np.arange(half_n)
    slope_recent, _ = np.polyfit(x_recent, y_recent, deg=1)

    mix_slope = (
        (1 - cfg["slope_weight_recent_ratio"]) * slope_all
        + cfg["slope_weight_recent_ratio"] * slope_recent
    )
    # 年化对数收益率：0.20 = 20%/年
    annual_log_ret = mix_slope * 250

    # 区间收益（用对数差反推，避免前复权失真）
    period_ret = (np.exp(y[-1] - y[0]) - 1) * 100

    # 最大回撤（对数价格 → 还原为比例）
    cum_max = np.maximum.accumulate(y)
    drawdown_arr = np.exp(y - cum_max) - 1
    max_dd = float(np.min(drawdown_arr))

    # 年化对数收益 20% → 90分；0% → 50分；-20% → 10分
    base_score = np.clip(50 + annual_log_ret * 200, 0, 100)
    dd_penalty = 0
    if max_dd < cfg["max_drawdown_sideways"]:
        dd_penalty = np.clip(abs(max_dd) * 100 * 0.6, 0, 40)
    final_score = np.clip(base_score - dd_penalty, 0, 100)

    if final_score >= 60 and max_dd > cfg["max_drawdown_sideways"]:
        label = "up"
    elif final_score <= 35 or max_dd < cfg["max_drawdown_down"]:
        label = "down"
    else:
        label = "sideways"

    return {
        "label": label,
        "score": round(float(final_score), 1),
        "slope_all": round(float(slope_all), 6),
        "slope_recent": round(float(slope_recent), 6),
        "max_dd": round(max_dd * 100, 2),
        "period_ret": round(float(period_ret), 2),
        "annual_log_ret": round(float(annual_log_ret), 4),
    }


def calc_multi_period_trend_from_df(df_raw: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    从批量历史K线 DataFrame 计算每只股票多周期趋势
    ✅ 解耦版：不再自己查SQL，数据由调用方（kline_repo）传入
    :param df_raw: DataFrame，字段 stock_code/trade_date/close
    :param cfg: TREND_CONFIG
    :return: DataFrame，字段 stock_code + trend_{short|mid|long}_{label|score}
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    out_rows = []
    for sc, group in df_raw.groupby("stock_code"):
        g = group.sort_values("trade_date").reset_index(drop=True)
        total_len = len(g)
        row = {"stock_code": sc}

        for period_key, label_key, score_key in [
            ("period_short", "trend_short_label", "trend_short_score"),
            ("period_mid", "trend_mid_label", "trend_mid_score"),
            ("period_long", "trend_long_label", "trend_long_score"),
        ]:
            p = cfg[period_key]
            if total_len >= p:
                ser = g["close"].tail(p).reset_index(drop=True)
                res = calc_trend_single_series(ser, cfg)
            else:
                res = {"label": "no_data", "score": 0}
            row[label_key] = res["label"]
            row[score_key] = res["score"]

        out_rows.append(row)

    return pd.DataFrame(out_rows)


def calc_multi_period_trend_batch(code_list: list, cfg: dict) -> pd.DataFrame:
    """
    【兼容旧接口】批量多周期趋势计算
    新代码建议直接调 calc_multi_period_trend_from_df，数据从 repo 传
    """
    from repository.kline_repo import get_batch_history_bars
    df_raw = get_batch_history_bars(code_list)
    return calc_multi_period_trend_from_df(df_raw, cfg)


def label_to_emoji(lab: str) -> str:
    """趋势标签转前端展示文本"""
    mapping = {
        "up": "📈上升",
        "sideways": "⏸️盘整",
        "down": "📉下降",
        "no_data": "📋数据不足",
    }
    return mapping.get(lab, lab)