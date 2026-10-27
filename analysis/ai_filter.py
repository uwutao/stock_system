import pandas as pd
import requests
from sqlalchemy import text
from database.db import engine
from config.settings import OLLAMA

def call_llm_stock_analysis(stock_code, stock_name, close, pct_chg, turnover):
    """批量筛选里的简短分析（旧函数保留）"""
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
    单只个股深度K线分析，重点K线盘面，pe/pb估值，行业；不预测涨跌
    stock_info: dict包含 name,code,close,pct_chg,turnover,peTTM,pbMRQ,industry
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
    """根据股票代码，查询最新一条K线+基础行业+pe/pb"""
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


def ai_stock_filter(min_price, max_price, max_count=20, use_llm=False):
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
    # LLM分析，只有勾选use_llm才执行
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
    # 写入ai_filter_record历史表
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
