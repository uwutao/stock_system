"""
文件：services/analysis_service.py
功能：筛选 + LLM分析 + 持久化 的编排层
职责：
  1. 调 filter_service.filter_candidates 拿候选
  2. 可选：并发调 LLM 做简短分析（失败降级，不阻塞）
  3. 持久化到 ai_filter_record
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.filter_service import filter_candidates
from services.llm_client import call_llm_stock_analysis
from repository.filter_repo import save_filter_records

logger = logging.getLogger(__name__)


def run_filter_with_analysis(
    min_price: float,
    max_price: float,
    max_count: int = 20,
    use_llm: bool = False,
    llm_workers: int = 4,
) -> pd.DataFrame:
    """
    编排：筛选 + 可选 LLM + 写库
    :param min_price: 价格下限
    :param max_price: 价格上限
    :param max_count: 最多返回条数
    :param use_llm: 是否调用 LLM 做简短分析
    :param llm_workers: LLM 并发线程数
    :return: 筛选结果 DataFrame
    """
    # 1) 纯筛选
    df = filter_candidates(min_price, max_price, max_count)
    if df.empty:
        return df

    # 2) LLM 分析：并发执行 + 失败降级，不阻塞主流程
    if use_llm:
        df["llm_analysis"] = _attach_llm_analysis(df, llm_workers)
    else:
        df["llm_analysis"] = None

    # 3) 持久化：失败只记日志，不影响返回
    try:
        rows = _to_record_rows(df, min_price, max_price, max_count, use_llm)
        save_filter_records(rows)
    except Exception as e:
        logger.warning(f"筛选记录持久化失败: {e}")

    # 4) DataFrame → dict 前的 NaN 清理
    return df.astype(object).where(pd.notnull(df), None)


def _attach_llm_analysis(df: pd.DataFrame, workers: int) -> list:
    """
    并发调用 LLM 生成简短分析
    :return: list[str]，与 df 行一一对应，失败项返回"分析失败"
    """
    results = [""] * len(df)
    df_reset = df.reset_index(drop=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                call_llm_stock_analysis,
                row["code"], row["name"], row["close"], row["pct_chg"], row["turnover"],
            ): idx
            for idx, row in df_reset.iterrows()
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                logger.warning(f"LLM分析异常 idx={idx}: {e}")
                results[idx] = "分析失败"
    return results


def _to_record_rows(df, min_price, max_price, max_count, use_llm) -> list:
    """DataFrame 行 → ai_filter_record 记录 dict 列表"""
    rows = []
    for _, row in df.iterrows():
        rows.append({
            "stock_code": row["code"],
            "ai_score": float(row["ai_total_score"]),
            "llm_analysis": row.get("llm_analysis"),
            "min_price": min_price,
            "max_price": max_price,
            "max_count": max_count,
            "use_llm": use_llm,
        })
    return rows