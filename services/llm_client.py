"""
文件：services/llm_client.py
功能：LLM 调用的唯一入口
职责：所有对 Ollama 的 HTTP 请求集中在这里
后续扩展：超时统一、重试、并发控制、速率限制都可以只改这一个文件
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import requests
from config.settings import OLLAMA


def call_llm_stock_analysis(stock_code, stock_name, close, pct_chg, turnover):
    """
    【批量筛选模式简短分析】
    入参：单只股票代码、名称、收盘价、涨跌幅、换手率
    返回：简短中文分析文本（150字以内）
    用途：前端勾选【开启批量简短AI分析】时批量调用
    """
    prompt = f"""
你是A股量化分析助手，请简要分析这只股票，输出简短中文分析，控制在150字以内。
股票：{stock_name}({stock_code})
最新收盘价：{close}
当日涨跌幅：{pct_chg}%
换手率：{turnover}%
输出要点：简要评价短期盘面，提示风险，不要预测涨跌。
    """
    payload = {"model": OLLAMA["model"], "prompt": prompt, "stream": False}
    try:
        resp = requests.post(OLLAMA["host"] + "/api/generate", json=payload, timeout=OLLAMA["timeout"])
        j = resp.json()
        return j.get("response", "LLM生成失败")
    except Exception as e:
        return f"LLM调用异常:{str(e)}"


def call_llm_single_deep_analysis(stock_info: dict):
    """
    【旧版深度分析：仅单日快照】保留兼容
    入参：stock_info dict，含当日 close/pct_chg/turnover/peTTM/pbMRQ/industry
    返回：dict {"think":思考过程, "content":分析文本}
    """
    name = stock_info["stock_name"]
    code = stock_info["stock_code"]
    close = stock_info["close"]
    pct_chg = stock_info["pct_chg"]
    turnover = stock_info["turnover"]
    pe = stock_info.get("peTTM")
    pb = stock_info.get("pbMRQ")
    industry = stock_info.get("industry", "未知行业")
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
4. 最后写2-3条风险提示；
5. 输出控制在400字以内，中文。
"""
    payload = {"model": OLLAMA["model"], "prompt": prompt, "stream": False}
    try:
        resp = requests.post(OLLAMA["host"] + "/api/generate", json=payload, timeout=OLLAMA["timeout"])
        j = resp.json()
        return {"think": j.get("thinking", ""), "content": j.get("response", "深度分析生成失败")}
    except Exception as e:
        return {"think": "", "content": f"LLM调用异常:{str(e)}"}


def call_llm_longterm_analysis(stats: dict):
    """
    【长周期综合LLM研判】
    入参：calc_stock_longterm_stats 输出的统计摘要 dict（无原始K线）
    返回：{"think":思考过程, "content":分析文本}
    Prompt 只喂统计汇总，token 占用很小
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
4. 提炼2-4条客观风险提示；
5. 全文450字以内，中文，禁止编造不存在的数据。
"""
    payload = {"model": OLLAMA["model"], "prompt": prompt, "stream": False}
    try:
        resp = requests.post(OLLAMA["host"] + "/api/generate", json=payload, timeout=OLLAMA["timeout"])
        j = resp.json()
        return {"think": j.get("thinking", ""), "content": j.get("response", "分析生成失败")}
    except Exception as e:
        return {"think": "", "content": f"LLM异常：{str(e)}"}