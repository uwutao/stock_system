# """
# ai_filter.py
# 功能模块：股票筛选 + LLM分析
# 1. ai_stock_filter：批量筛选，基于当日指标打分，供前端【执行筛选】按钮调用（原有逻辑保留）
# 2. call_llm_stock_analysis：批量模式简短AI分析，仅当日少量指标，150字简短输出
# 3. get_single_stock_info：获取单只股票最新单日K线+行业估值（旧接口兼容，保留备用）
# 4. calc_stock_longterm_stats：【新增】读取最多750根交易日K线（约3年），pandas计算长周期统计指标
#    ！重要：原始K线只用于程序计算，不会直接丢给大模型，避免token爆炸
# 5. call_llm_longterm_analysis：【新增】接收长周期统计摘要dict，交给LLM做综合研判，不喂原始K线
# 6. call_llm_single_deep_analysis：旧版深度分析（仅单日快照，保留兼容，后续接口切换为长周期版本）
# """
# import pandas as pd
# import requests
# import numpy as np
# from sqlalchemy import text
# from database.db import engine
# from config.settings import OLLAMA, TREND_CONFIG


# def call_llm_stock_analysis(stock_code, stock_name, close, pct_chg, turnover):
#     """
#     【批量筛选模式简短分析】旧函数保留
#     入参：单只股票代码、名称、收盘价、涨跌幅、换手率
#     返回：简短中文分析文本(150字以内)
#     用途：前端勾选【开启批量简短AI分析】时批量调用，只使用当日快照指标
#     """
#     prompt = f"""
# 你是A股量化分析助手，请简要分析这只股票，输出简短中文分析，控制在150字以内。
# 股票：{stock_name}({stock_code})
# 最新收盘价：{close}
# 当日涨跌幅：{pct_chg}%
# 换手率：{turnover}%
# 输出要点：简要评价短期盘面，提示风险，不要预测涨跌。
#     """
#     payload = {
#         "model": OLLAMA["model"],
#         "prompt": prompt,
#         "stream": False
#     }
#     try:
#         resp = requests.post(OLLAMA["host"] + "/api/generate", json=payload, timeout=OLLAMA["timeout"])
#         j = resp.json()
#         return j.get("response", "LLM生成失败")
#     except Exception as e:
#         return f"LLM调用异常:{str(e)}"


# def call_llm_single_deep_analysis(stock_info: dict):
#     """
#     【旧版深度分析：仅单日快照】保留用于兼容
#     入参：stock_info dict，包含当日close/pct_chg/turnover/peTTM/pbMRQ/industry
#     返回dict {"think":模型思考过程,"content":分析文本}
#     限制：只看最新一根K线，没有历史时序数据，分析能力有限；推荐使用calc_stock_longterm_stats + call_llm_longterm_analysis
#     """
#     name = stock_info["stock_name"]
#     code = stock_info["stock_code"]
#     close = stock_info["close"]
#     pct_chg = stock_info["pct_chg"]
#     turnover = stock_info["turnover"]
#     pe = stock_info.get("peTTM")
#     pb = stock_info.get("pbMRQ")
#     industry = stock_info.get("industry", "未知行业")
#     prompt = f"""
# 你是A股K线量化分析师，基于下面个股数据做深度盘面分析，**禁止预测未来涨跌**，只客观解读当前K线盘面特征、资金情绪、估值状态，最后给出风险提示。
# 【股票信息】
# 名称：{name} 代码：{code}
# 所属行业：{industry}
# 最新收盘价：{close}
# 当日涨跌幅：{pct_chg}%
# 换手率：{turnover}%
# 滚动市盈率peTTM：{pe if pe is not None else "无数据"}
# 市净率pbMRQ：{pb if pb is not None else "无数据"}
# 分析要求：
# 1. 重点从K线盘面、换手率活跃度、估值水平角度解读；
# 2. 区分高换手/低换手代表的资金状态；
# 3. 客观说明当前盘面现象，严禁给出买入、卖出、持仓的确定性建议；
# 4. 最后写2‑3条风险提示；
# 5. 输出控制在400字以内，中文。
# """
#     payload = {
#         "model": OLLAMA["model"],
#         "prompt": prompt,
#         "stream": False
#     }
#     try:
#         resp = requests.post(OLLAMA["host"] + "/api/generate", json=payload, timeout=OLLAMA["timeout"])
#         j = resp.json()
#         think = j.get("thinking", "")
#         res_text = j.get("response", "深度分析生成失败")
#         return {"think": think, "content": res_text}
#     except Exception as e:
#         return {"think": "", "content": f"LLM调用异常:{str(e)}"}


# def get_single_stock_info(stock_code: str):
#     """
#     获取单只股票【最新单日一条K线】+行业+pe/pb
#     返回dict；无数据返回None
#     兼容旧接口使用；⚠️仅单日快照，不包含历史时序
#     """
#     sql = text("""
#     SELECT d.stock_code,d.stock_name,d.close,d.pct_chg,d.turnover,d.peTTM,d.pbMRQ,b.industry
#     FROM daily_kline d
#     LEFT JOIN stock_basic b ON d.stock_code = b.stock_code
#     WHERE d.stock_code = :sc
#     ORDER BY d.trade_date DESC LIMIT 1
#     """)
#     with engine.connect() as conn:
#         row = conn.execute(sql, {"sc": stock_code}).mappings().first()
#         if not row:
#             return None
#         return dict(row)


# def calc_stock_longterm_stats(stock_code: str):
#     """
#     ✨【新增核心函数】长周期指标计算
#     读取最多750个交易日K线(≈3年)，pandas做定量统计计算
#     返回结构化统计字典；历史交易日不足120天返回None(数据太少不做分析)
#     逻辑：原始K线仅用于程序数学运算，**不把几百行原始K线文本丢进LLM**，规避token上限、幻觉、推理慢问题
#     输出字段：3年涨跌幅、价格分位、最大回撤、250日平均换手、PE/PB历史分位等数值摘要
#     """
#     sql_kline = text("""
#         SELECT trade_date,open,high,low,close,volume,turnover,pct_chg,peTTM,pbMRQ
#         FROM daily_kline
#         WHERE stock_code=:sc
#         ORDER BY trade_date ASC LIMIT 750
#     """)
#     sql_basic = text("""
#         SELECT stock_name,industry FROM stock_basic WHERE stock_code=:sc
#     """)
#     with engine.connect() as conn:
#         res_k = conn.execute(sql_kline, {"sc": stock_code})
#         df = pd.DataFrame(res_k.mappings().all())
#         if df.shape[0] < 120:
#             return None
#         res_b = conn.execute(sql_basic, {"sc": stock_code}).mappings().first()
#     df = df.sort_values("trade_date").reset_index(drop=True)

#     def to_none_if_nan(val):
#         if pd.isna(val):
#             return None
#         return float(val)

#     start_price = df["close"].iloc[0]
#     latest_price = df["close"].iloc[-1]
#     max_price_3y = df["high"].max()
#     min_price_3y = df["low"].min()

#     total_return_3y = round(((latest_price / start_price) - 1) * 100, 2)
#     price_percentile_3y = round(((latest_price - min_price_3y) / (max_price_3y - min_price_3y)) * 100, 2)

#     df["cum_max"] = df["close"].cummax()
#     df["drawdown"] = (df["close"] / df["cum_max"] - 1) * 100
#     max_drawdown_3y = round(df["drawdown"].min(), 2)

#     turnover_mean_250 = round(df["turnover"].tail(250).mean(), 2)

#     if "peTTM" in df.columns:
#         pe_latest = df["peTTM"].iloc[-1]
#         pe_series = df["peTTM"].dropna()
#     else:
#         pe_latest = None
#         pe_series = pd.Series(dtype="float64")

#     if "pbMRQ" in df.columns:
#         pb_latest = df["pbMRQ"].iloc[-1]
#         pb_series = df["pbMRQ"].dropna()
#     else:
#         pb_latest = None
#         pb_series = pd.Series(dtype="float64")

#     pe_pct = None
#     pb_pct = None
#     if len(pe_series) > 30 and not pd.isna(pe_latest):
#         cnt_less = (pe_series < pe_latest).sum()
#         pe_pct = round((cnt_less / len(pe_series)) * 100, 1)
#     if len(pb_series) > 30 and not pd.isna(pb_latest):
#         cnt_less = (pb_series < pb_latest).sum()
#         pb_pct = round((cnt_less / len(pb_series)) * 100, 1)

#     stats = {
#         "stock_code": stock_code,
#         "stock_name": res_b["stock_name"] if res_b else "",
#         "industry": res_b["industry"] if res_b else "未知",
#         "data_days": len(df),
#         "latest_price": to_none_if_nan(latest_price),
#         "total_return_3y_pct": to_none_if_nan(total_return_3y),
#         "price_3y_percentile": to_none_if_nan(price_percentile_3y),
#         "max_price_3y": to_none_if_nan(max_price_3y),
#         "min_price_3y": to_none_if_nan(min_price_3y),
#         "max_drawdown_3y_pct": to_none_if_nan(max_drawdown_3y),
#         "turnover_mean_250": to_none_if_nan(turnover_mean_250),
#         "pe_latest": to_none_if_nan(pe_latest),
#         "pe_3y_percentile": pe_pct,
#         "pb_latest": to_none_if_nan(pb_latest),
#         "pb_3y_percentile": pb_pct
#     }
#     return stats


# def call_llm_longterm_analysis(stats: dict):
#     """
#     ✨【新增】长周期综合LLM研判
#     入参：calc_stock_longterm_stats输出的统计摘要dict（全部是计算好的数值，无原始K线）
#     返回：{"think":思考过程,"content":分析文本}
#     Prompt只喂统计汇总结果，token占用很小，不受上下文窗口限制；
#     任务：解读3年收益、回撤、价格位置、换手活跃度、估值分位；禁止预测涨跌，禁止买卖建议
#     """
#     name = stats["stock_name"]
#     code = stats["stock_code"]
#     industry = stats["industry"]
#     prompt = f"""
# 你是A股量化分析师，基于下面这只股票近3年统计汇总数据做综合盘面研判。
# ⚠️禁止预测未来涨跌，不给出买入/卖出/持仓建议，只客观解读历史特征、估值位置、风险。
# 【标的信息】
# 股票：{name}({code})
# 行业：{industry}
# 有效历史交易日：{stats['data_days']}天
# 【价格与收益统计（近3年）】
# 近3年总涨跌幅：{stats['total_return_3y_pct']}%
# 现价处于近3年价格分位：{stats['price_3y_percentile']:.1f}%（0=历史最低，100=历史最高）
# 3年区间最高：{stats['max_price_3y']}，区间最低：{stats['min_price_3y']}
# 近三年最大回撤：{stats['max_drawdown_3y_pct']}%
# 【量能】
# 近250日平均换手率：{stats['turnover_mean_250']}%
# 【估值】
# 滚动市盈率PE(TTM)：{stats['pe_latest'] if stats['pe_latest'] is not None else "无数据"}
# PE近3年历史分位：{stats['pe_3y_percentile'] if stats['pe_3y_percentile'] is not None else "无数据"}%
# 市净率PB(MRQ)：{stats['pb_latest'] if stats['pb_latest'] is not None else "无数据"}
# PB近3年历史分位：{stats['pb_3y_percentile'] if stats['pb_3y_percentile'] is not None else "无数据"}%
# 分析任务：
# 1. 解读近3年价格表现：收益、回撤、当前价格所处历史位置；
# 2. 结合换手率评价历史资金活跃度；
# 3. 结合PE/PB历史分位评价估值水平；
# 4. 提炼2‑4条客观风险提示；
# 5. 全文450字以内，中文，禁止编造不存在的数据。
# """
#     payload = {
#         "model": OLLAMA["model"],
#         "prompt": prompt,
#         "stream": False
#     }
#     try:
#         resp = requests.post(OLLAMA["host"] + "/api/generate", json=payload, timeout=OLLAMA["timeout"])
#         j = resp.json()
#         think = j.get("thinking", "")
#         content = j.get("response", "分析生成失败")
#         return {"think": think, "content": content}
#     except Exception as e:
#         return {"think": "", "content": f"LLM异常：{str(e)}"}


# def ai_stock_filter(min_price, max_price, max_count=20, use_llm=False):
#     """
#     【批量股票筛选主函数】 升级：多周期趋势加权打分
#     逻辑：
#     1. DISTINCT ON拿每只股票最新一条日线，过滤ST
#     2. 价格区间过滤
#     3. 批量查询多周期趋势（40/250/750），groupby批量计算
#     4. 权重：趋势为主，单日量价占比由配置控制；加权合成ai_total_score总分数
#     5. 按总分数降序取max_count条
#     6. use_llm=True：循环调用call_llm_stock_analysis生成简短AI文本
#     7. 结果写入ai_filter_record历史记录表
#     返回pandas DataFrame，给到app.py转为json返回前端
#     """
#     cfg = TREND_CONFIG
#     sql = text("""
#     SELECT DISTINCT ON(d.stock_code)
#         d.stock_code,d.stock_name,d.trade_date,
#         d.close::double precision AS close,
#         d.volume::double precision AS volume,
#         d.turnover::double precision AS turnover,
#         d.pct_chg::double precision AS pct_chg,
#         b.industry
#     FROM daily_kline d
#     LEFT JOIN stock_basic b ON d.stock_code = b.stock_code
#     WHERE d.isST <> '1'
#     ORDER BY d.stock_code, d.trade_date DESC;
#     """)
#     with engine.connect() as conn:
#         result = conn.execute(sql)
#         rows = result.mappings().all()
#         df_latest = pd.DataFrame(rows)

#     if df_latest.empty:
#         return pd.DataFrame()

#     df_latest = df_latest[(df_latest["close"] >= min_price) & (df_latest["close"] <= max_price)]
#     if df_latest.empty:
#         return pd.DataFrame()

#     # ========= 1、计算旧的单日快照分数 =========
#     def calc_single_day_score(row):
#         score = 0
#         pct_chg = row["pct_chg"]
#         volume = row["volume"]
#         turnover = row["turnover"]
#         if pct_chg > 0:
#             score += 20
#             if pct_chg > 2:
#                 score += 10
#             if pct_chg > 4:
#                 score += 10
#         elif pct_chg < -2:
#             score -= 10
#         if volume > 0:
#             score += 10
#         if 1 < turnover < 8:
#             score += 15
#         if turnover > 15:
#             score -= 10
#         score = max(0, min(score, 100))
#         return score

#     df_latest["single_day_score"] = df_latest.apply(calc_single_day_score, axis=1)

#     # ========= 2、批量获取多周期趋势，一次SQL，groupby计算 =========
#     code_list = df_latest["stock_code"].tolist()
#     df_trend = calc_multi_period_trend_batch(code_list, cfg)
#     df_merge = pd.merge(df_latest, df_trend, left_on="stock_code", right_on="stock_code", how="left")

#     # =========3、加权合成总分数 =========
#     def calc_total_weight_score(r):
#         """
#         加权合成综合趋势总分
#         :param r: dataframe行数据
#         :return: 加权分数0~100
#         """
#         w_s = cfg["weight_short"]
#         w_m = cfg["weight_mid"]
#         w_l = cfg["weight_long"]
#         w_day = cfg["weight_single_day"]

#         real_w_short = w_s if r["trend_short_label"] != "no_data" else 0
#         real_w_mid = w_m if r["trend_mid_label"] != "no_data" else 0
#         real_w_long = w_l if r["trend_long_label"] != "no_data" else 0

#         w_sum = real_w_short + real_w_mid + real_w_long + w_day
#         if w_sum <= 0:
#             return 0

#         total = (
#             r["trend_short_score"] * real_w_short
#             + r["trend_mid_score"] * real_w_mid
#             + r["trend_long_score"] * real_w_long
#             + r["single_day_score"] * w_day
#         ) / w_sum
#         return round(total, 1)

#     df_merge["ai_total_score"] = df_merge.apply(calc_total_weight_score, axis=1)
#     df_merge = df_merge[df_merge["ai_total_score"] > 0].sort_values("ai_total_score", ascending=False).head(max_count)

#     # emoji标签转换
#     def label_emoji(lab):
#         mapping = {"up": "📈上升", "sideways": "⏸️盘整", "down": "📉下降", "no_data": "📋数据不足"}
#         return mapping.get(lab, lab)

#     df_merge["trend_short_text"] = df_merge["trend_short_label"].apply(label_emoji)
#     df_merge["trend_mid_text"] = df_merge["trend_mid_label"].apply(label_emoji)
#     df_merge["trend_long_text"] = df_merge["trend_long_label"].apply(label_emoji)

#     df_merge.rename(columns={"stock_code": "code", "stock_name": "name"}, inplace=True)

#     llm_text_list = []
#     if use_llm:
#         for _, row in df_merge.iterrows():
#             txt = call_llm_stock_analysis(
#                 row["code"], row["name"], row["close"], row["pct_chg"], row["turnover"]
#             )
#             llm_text_list.append(txt)
#         df_merge["llm_analysis"] = llm_text_list
#     else:
#         df_merge["llm_analysis"] = None

#     insert_rows = []
#     for _, row in df_merge.iterrows():
#         insert_rows.append({
#             "stock_code": row["code"],
#             "ai_score": float(row["ai_total_score"]),
#             "llm_analysis": row["llm_analysis"],
#             "min_price": min_price,
#             "max_price": max_price,
#             "max_count": max_count,
#             "use_llm": use_llm
#         })
#     if len(insert_rows) > 0:
#         with engine.connect() as conn:
#             conn.execute(text("""
# INSERT INTO ai_filter_record(stock_code,ai_score,llm_analysis,min_price,max_price,max_count,use_llm)
# VALUES(:stock_code,:ai_score,:llm_analysis,:min_price,:max_price,:max_count,:use_llm)
#             """), insert_rows)
#             conn.commit()

#     df_out = df_merge.astype(object).where(pd.notnull(df_merge), None)
#     return df_out


# def calc_trend_single_series(close_ser: pd.Series, cfg: dict):
#     """
#     计算单段收盘价序列趋势
#     :param close_ser: 收盘价Series，已经前复权，时间升序
#     :param cfg: TREND_CONFIG配置字典
#     :return: dict {label, score, slope_all, slope_recent, max_dd, period_ret}
#     label: up / sideways / down / no_data
#     """
#     n = len(close_ser)
#     if n < 10:
#         return {
#             "label": "no_data",
#             "score": 0,
#             "slope_all": None,
#             "slope_recent": None,
#             "max_dd": None,
#             "period_ret": None
#         }
#     y = close_ser.values
#     x = np.arange(n)
#     slope_all, _ = np.polyfit(x, y, deg=1)

#     half_n = max(n // 2, 10)
#     y_recent = y[-half_n:]
#     x_recent = np.arange(half_n)
#     slope_recent, _ = np.polyfit(x_recent, y_recent, deg=1)

#     mix_slope = (1 - cfg["slope_weight_recent_ratio"]) * slope_all + cfg["slope_weight_recent_ratio"] * slope_recent
#     period_ret = (y[-1] / y[0] - 1) * 100

#     cum_max = np.maximum.accumulate(y)
#     drawdown_arr = y / cum_max - 1
#     max_dd = float(np.min(drawdown_arr))

#     base_score = np.clip(50 + mix_slope * 250, 0, 100)
#     dd_penalty = 0
#     if max_dd < cfg["max_drawdown_sideways"]:
#         dd_penalty = np.clip(abs(max_dd) * 100 * 0.6, 0, 40)
#     final_score = np.clip(base_score - dd_penalty, 0, 100)

#     if final_score >= 60 and max_dd > cfg["max_drawdown_sideways"]:
#         label = "up"
#     elif final_score <= 35 or max_dd < cfg["max_drawdown_down"]:
#         label = "down"
#     else:
#         label = "sideways"

#     return {
#         "label": label,
#         "score": round(float(final_score), 1),
#         "slope_all": round(float(slope_all), 4),
#         "slope_recent": round(float(slope_recent), 4),
#         "max_dd": round(max_dd * 100, 2),
#         "period_ret": round(float(period_ret), 2)
#     }


# def calc_multi_period_trend_batch(code_list: list, cfg: dict):
#     """
#     ✅【批量多周期趋势计算，性能优先】
#     一次性IN查询一批股票全部日线，groupby分组批量计算；禁止循环单只股票查SQL
#     :param code_list: 股票代码list
#     :param cfg: TREND_CONFIG
#     :return: df，字段：trend_xxx
#     """
#     sql = text("""
#         SELECT stock_code, trade_date, close
#         FROM daily_kline
#         WHERE stock_code IN :code_arr
#         ORDER BY stock_code, trade_date ASC
#     """)
#     with engine.connect() as conn:
#         res = conn.execute(sql, {"code_arr": tuple(code_list)})
#         df_raw = pd.DataFrame(res.mappings().all())
#         if "close" in df_raw.columns:
#             df_raw["close"] = df_raw["close"].astype(float)

#     if df_raw.empty:
#         return pd.DataFrame()

#     out_rows = []
#     for sc, group in df_raw.groupby("stock_code"):
#         g = group.reset_index(drop=True)
#         total_len = len(g)
#         row = {"stock_code": sc}

#         p_short = cfg["period_short"]
#         if total_len >= p_short:
#             ser_s = g["close"].tail(p_short)
#             res_s = calc_trend_single_series(ser_s, cfg)
#         else:
#             res_s = {"label": "no_data", "score": 0}
#         row["trend_short_label"] = res_s["label"]
#         row["trend_short_score"] = res_s["score"]

#         p_mid = cfg["period_mid"]
#         if total_len >= p_mid:
#             ser_m = g["close"].tail(p_mid)
#             res_m = calc_trend_single_series(ser_m, cfg)
#         else:
#             res_m = {"label": "no_data", "score": 0}
#         row["trend_mid_label"] = res_m["label"]
#         row["trend_mid_score"] = res_m["score"]

#         p_long = cfg["period_long"]
#         if total_len >= p_long:
#             ser_l = g["close"].tail(p_long)
#             res_l = calc_trend_single_series(ser_l, cfg)
#         else:
#             res_l = {"label": "no_data", "score": 0}
#         row["trend_long_label"] = res_l["label"]
#         row["trend_long_score"] = res_l["score"]

#         out_rows.append(row)
#     df_out = pd.DataFrame(out_rows)
#     return df_out
