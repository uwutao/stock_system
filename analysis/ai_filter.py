"""
ai_filter.py
功能模块：股票筛选 + LLM分析
1. ai_stock_filter：批量筛选，基于当日指标打分，供前端【执行筛选】按钮调用（原有逻辑保留）
2. call_llm_stock_analysis：批量模式简短AI分析，仅当日少量指标，150字简短输出
3. get_single_stock_info：获取单只股票最新单日K线+行业估值（旧接口兼容，保留备用）
4. calc_stock_longterm_stats：【新增】读取最多750根交易日K线（约3年），pandas计算长周期统计指标
   ！重要：原始K线只用于程序计算，不会直接丢给大模型，避免token爆炸
5. call_llm_longterm_analysis：【新增】接收长周期统计摘要dict，交给LLM做综合研判，不喂原始K线
6. call_llm_single_deep_analysis：旧版深度分析（仅单日快照，保留兼容，后续接口切换为长周期版本）
"""
import pandas as pd
import requests
from sqlalchemy import text
from database.db import engine
from config.settings import OLLAMA


def call_llm_stock_analysis(stock_code, stock_name, close, pct_chg, turnover):
    """
    【批量筛选模式简短分析】旧函数保留
    入参：单只股票代码、名称、收盘价、涨跌幅、换手率
    返回：简短中文分析文本(150字以内)
    用途：前端勾选【开启批量简短AI分析】时批量调用，只使用当日快照指标
    """
    prompt = f"""
你是A股量化分析助手，请简要分析这只股票，输出简短中文分析，控制在150字以内。
股票：{stock_name}({stock_code})
最新收盘价：{close}
当日涨跌幅：{pct_chg}%
换手率：{turnover}%
输出要点：简要评价短期盘面，提示风险，不要预测涨跌。
    """
    payload = {
        "model": OLLAMA["model"],
        "prompt": prompt,
        "stream": False
    }
    try:
        resp = requests.post(OLLAMA["host"]+"/api/generate", json=payload, timeout=OLLAMA["timeout"])
        j = resp.json()
        return j.get("response","LLM生成失败")
    except Exception as e:
        return f"LLM调用异常:{str(e)}"


def call_llm_single_deep_analysis(stock_info:dict):
    """
    【旧版深度分析：仅单日快照】保留用于兼容
    入参：stock_info dict，包含当日close/pct_chg/turnover/peTTM/pbMRQ/industry
    返回dict {"think":模型思考过程,"content":分析文本}
    限制：只看最新一根K线，没有历史时序数据，分析能力有限；推荐使用calc_stock_longterm_stats + call_llm_longterm_analysis
    """
    name = stock_info["stock_name"]
    code = stock_info["stock_code"]
    close = stock_info["close"]
    pct_chg = stock_info["pct_chg"]
    turnover = stock_info["turnover"]
    pe = stock_info.get("peTTM")
    pb = stock_info.get("pbMRQ")
    industry = stock_info.get("industry","未知行业")
    prompt = f"""
你是A股K线量化分析师，基于下面个股数据做深度盘面分析，**禁止预测未来涨跌**，只客观解读当前K线盘面特征、资金情绪、估值状态，最后给出风险提示。
【股票信息】
名称：{name} 代码：{code}
所属行业：{industry}
最新收盘价：{close}
当日涨跌幅：{pct_chg}%
换手率：{turnover}%
滚动市盈率peTTM：{pe if pe is not None else "无数据"}
市净率pbMRQ：{pb if pb is not None else "无数据"}
分析要求：
1. 重点从K线盘面、换手率活跃度、估值水平角度解读；
2. 区分高换手/低换手代表的资金状态；
3. 客观说明当前盘面现象，严禁给出买入、卖出、持仓的确定性建议；
4. 最后写2‑3条风险提示；
5. 输出控制在400字以内，中文。
"""
    payload = {
        "model": OLLAMA["model"],
        "prompt": prompt,
        "stream": False
    }
    try:
        resp = requests.post(OLLAMA["host"]+"/api/generate", json=payload, timeout=OLLAMA["timeout"])
        j = resp.json()
        think = j.get("thinking","")
        res_text = j.get("response","深度分析生成失败")
        return {"think":think,"content":res_text}
    except Exception as e:
        return {"think":"","content":f"LLM调用异常:{str(e)}"}


def get_single_stock_info(stock_code:str):
    """
    获取单只股票【最新单日一条K线】+行业+pe/pb
    返回dict；无数据返回None
    兼容旧接口使用；⚠️仅单日快照，不包含历史时序
    """
    sql = text("""
    SELECT d.stock_code,d.stock_name,d.close,d.pct_chg,d.turnover,d.peTTM,d.pbMRQ,b.industry
    FROM daily_kline d
    LEFT JOIN stock_basic b ON d.stock_code = b.stock_code
    WHERE d.stock_code = :sc
    ORDER BY d.trade_date DESC LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql,{"sc":stock_code}).mappings().first()
        if not row:
            return None
        return dict(row)


def calc_stock_longterm_stats(stock_code: str):
    """
    ✨【新增核心函数】长周期指标计算
    读取最多750个交易日K线(≈3年)，pandas做定量统计计算
    返回结构化统计字典；历史交易日不足120天返回None(数据太少不做分析)
    逻辑：原始K线仅用于程序数学运算，**不把几百行原始K线文本丢进LLM**，规避token上限、幻觉、推理慢问题
    输出字段：3年涨跌幅、价格分位、最大回撤、250日平均换手、PE/PB历史分位等数值摘要
    """
    import numpy as np
    sql_kline = text("""
        SELECT trade_date,open,high,low,close,volume,turnover,pct_chg,peTTM,pbMRQ
        FROM daily_kline
        WHERE stock_code=:sc
        ORDER BY trade_date ASC LIMIT 750
    """)
    sql_basic = text("""
        SELECT stock_name,industry FROM stock_basic WHERE stock_code=:sc
    """)
    with engine.connect() as conn:
        res_k = conn.execute(sql_kline, {"sc": stock_code})
        df = pd.DataFrame(res_k.mappings().all())
        # 历史数据不足120个交易日直接返回None
        if df.shape[0] < 120:
            return None
        res_b = conn.execute(sql_basic, {"sc": stock_code}).mappings().first()

    df = df.sort_values("trade_date").reset_index(drop=True)

    # 工具函数：把np.nan / pd.NA全部转为Python原生None，保证JSON可序列化
    def to_none_if_nan(val):
        if pd.isna(val):
            return None
        return float(val)

    # --------价格类，必有的列 --------
    start_price = df["close"].iloc[0]
    latest_price = df["close"].iloc[-1]
    max_price_3y = df["high"].max()
    min_price_3y = df["low"].min()

    # 近3年总涨跌幅
    total_return_3y = round(((latest_price / start_price) - 1) * 100, 2)
    # 当前价格在3年高低点分位 0~100
    price_percentile_3y = round(((latest_price - min_price_3y) / (max_price_3y - min_price_3y)) * 100, 2)

    # 简单最大回撤计算
    df["cum_max"] = df["close"].cummax()
    df["drawdown"] = (df["close"] / df["cum_max"] - 1) * 100
    max_drawdown_3y = round(df["drawdown"].min(), 2)

    # 近250个交易日平均换手率
    turnover_mean_250 = round(df["turnover"].tail(250).mean(), 2)

    # ========== 【重点修复】安全获取peTTM / pbMRQ，列不存在直接置空 ==========
    if "peTTM" in df.columns:
        pe_latest = df["peTTM"].iloc[-1]
        pe_series = df["peTTM"].dropna()
    else:
        pe_latest = None
        pe_series = pd.Series(dtype="float64")

    if "pbMRQ" in df.columns:
        pb_latest = df["pbMRQ"].iloc[-1]
        pb_series = df["pbMRQ"].dropna()
    else:
        pb_latest = None
        pb_series = pd.Series(dtype="float64")

    pe_pct = None
    pb_pct = None
    # 手动计算PE历史百分位：当前pe在历史样本里面所处位置
    if len(pe_series) > 30 and not pd.isna(pe_latest):
        cnt_less = (pe_series < pe_latest).sum()
        pe_pct = round((cnt_less / len(pe_series)) * 100, 1)

    if len(pb_series) > 30 and not pd.isna(pb_latest):
        cnt_less = (pb_series < pb_latest).sum()
        pb_pct = round((cnt_less / len(pb_series)) * 100, 1)

    stats = {
        "stock_code": stock_code,
        "stock_name": res_b["stock_name"] if res_b else "",
        "industry": res_b["industry"] if res_b else "未知",
        "data_days": len(df),
        "latest_price": to_none_if_nan(latest_price),
        "total_return_3y_pct": to_none_if_nan(total_return_3y),
        "price_3y_percentile": to_none_if_nan(price_percentile_3y),
        "max_price_3y": to_none_if_nan(max_price_3y),
        "min_price_3y": to_none_if_nan(min_price_3y),
        "max_drawdown_3y_pct": to_none_if_nan(max_drawdown_3y),
        "turnover_mean_250": to_none_if_nan(turnover_mean_250),
        "pe_latest": to_none_if_nan(pe_latest),
        "pe_3y_percentile": pe_pct,
        "pb_latest": to_none_if_nan(pb_latest),
        "pb_3y_percentile": pb_pct
    }
    return stats



def call_llm_longterm_analysis(stats: dict):
    """
    ✨【新增】长周期综合LLM研判
    入参：calc_stock_longterm_stats输出的统计摘要dict（全部是计算好的数值，无原始K线）
    返回：{"think":思考过程,"content":分析文本}
    Prompt只喂统计汇总结果，token占用很小，不受上下文窗口限制；
    任务：解读3年收益、回撤、价格位置、换手活跃度、估值分位；禁止预测涨跌，禁止买卖建议
    """
    name = stats["stock_name"]
    code = stats["stock_code"]
    industry = stats["industry"]

    prompt = f"""
你是A股量化分析师，基于下面这只股票近3年统计汇总数据做综合盘面研判。
⚠️禁止预测未来涨跌，不给出买入/卖出/持仓建议，只客观解读历史特征、估值位置、风险。

【标的信息】
股票：{name}({code})
行业：{industry}
有效历史交易日：{stats['data_days']}天

【价格与收益统计（近3年）】
近3年总涨跌幅：{stats['total_return_3y_pct']}%
现价处于近3年价格分位：{stats['price_3y_percentile']:.1f}%（0=历史最低，100=历史最高）
3年区间最高：{stats['max_price_3y']}，区间最低：{stats['min_price_3y']}
近三年最大回撤：{stats['max_drawdown_3y_pct']}%

【量能】
近250日平均换手率：{stats['turnover_mean_250']}%

【估值】
滚动市盈率PE(TTM)：{stats['pe_latest'] if stats['pe_latest'] is not None else "无数据"}
PE近3年历史分位：{stats['pe_3y_percentile'] if stats['pe_3y_percentile'] is not None else "无数据"}%
市净率PB(MRQ)：{stats['pb_latest'] if stats['pb_latest'] is not None else "无数据"}
PB近3年历史分位：{stats['pb_3y_percentile'] if stats['pb_3y_percentile'] is not None else "无数据"}%

分析任务：
1. 解读近3年价格表现：收益、回撤、当前价格所处历史位置；
2. 结合换手率评价历史资金活跃度；
3. 结合PE/PB历史分位评价估值水平；
4. 提炼2‑4条客观风险提示；
5. 全文450字以内，中文，禁止编造不存在的数据。
"""
    payload = {
        "model": OLLAMA["model"],
        "prompt": prompt,
        "stream": False
    }
    try:
        resp = requests.post(OLLAMA["host"]+"/api/generate", json=payload, timeout=OLLAMA["timeout"])
        j = resp.json()
        think = j.get("thinking","")
        content = j.get("response","分析生成失败")
        return {"think":think,"content":content}
    except Exception as e:
        return {"think":"","content":f"LLM异常：{str(e)}"}


def ai_stock_filter(min_price, max_price, max_count=20, use_llm=False):
    """
    【批量股票筛选主函数】前端页面【执行筛选】调用
    逻辑：
    1. DISTINCT ON拿每只股票最新一条日线，过滤ST
    2. 价格区间过滤，自定义简易打分calc_score
    3. 按分数降序取max_count条
    4. use_llm=True：循环调用call_llm_stock_analysis生成简短AI文本
    5. 结果写入ai_filter_record历史记录表
    返回pandas DataFrame，给到app.py转为json返回前端
    ⚠️注意：本函数打分只使用**当日快照指标**，没有用到2‑3年长周期统计；长周期统计点击【深度K线分析】按钮触发
    """
    sql = text("""
    SELECT DISTINCT ON(d.stock_code)
        d.stock_code,d.stock_name,d.trade_date,
        d.close::double precision AS close,
        d.volume::double precision AS volume,
        d.turnover::double precision AS turnover,
        d.pct_chg::double precision AS pct_chg,
        b.industry
    FROM daily_kline d
    LEFT JOIN stock_basic b ON d.stock_code = b.stock_code
    WHERE d.isST <> '1'
    ORDER BY d.stock_code, d.trade_date DESC;
    """)
    with engine.connect() as conn:
        result = conn.execute(sql)
        rows = result.mappings().all()
        df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()
    df = df[(df["close"] >= min_price) & (df["close"] <= max_price)]

    def calc_score(row):
        """单只股票简易打分函数：仅使用当日行情指标，0‑100分"""
        score = 0
        pct_chg = row["pct_chg"]
        volume = row["volume"]
        turnover = row["turnover"]
        if pct_chg > 0:
            score += 20
            if pct_chg > 2:
                score += 10
            if pct_chg >4:
                score +=10
        elif pct_chg < -2:
            score -=10
        if volume >0:
            score +=10
        if 1 < turnover <8:
            score +=15
        if turnover>15:
            score -=10
        score = max(0,min(score,100))
        return score

    df["ai_score"] = df.apply(calc_score,axis=1)
    df = df[df["ai_score"]>0].sort_values("ai_score",ascending=False).head(max_count)
    df.rename(columns={"stock_code":"code","stock_name":"name"},inplace=True)

    # LLM简短分析，只有勾选use_llm才执行
    llm_text_list = []
    if use_llm:
        for _,row in df.iterrows():
            txt = call_llm_stock_analysis(
                row["code"],row["name"],row["close"],row["pct_chg"],row["turnover"]
            )
            llm_text_list.append(txt)
        df["llm_analysis"] = llm_text_list
    else:
        df["llm_analysis"] = None

    # 写入ai_filter_record筛选历史表
    insert_rows = []
    for _,row in df.iterrows():
        insert_rows.append({
            "stock_code":row["code"],
            "ai_score":int(row["ai_score"]),
            "llm_analysis":row["llm_analysis"],
            "min_price":min_price,
            "max_price":max_price,
            "max_count":max_count,
            "use_llm":use_llm
        })
    if len(insert_rows)>0:
        with engine.connect() as conn:
            conn.execute(text("""
INSERT INTO ai_filter_record(stock_code,ai_score,llm_analysis,min_price,max_price,max_count,use_llm)
VALUES(:stock_code,:ai_score,:llm_analysis,:min_price,:max_price,:max_count,:use_llm)
            """),insert_rows)
            conn.commit()
    df = df.astype(object).where(pd.notnull(df), None)
    return df
