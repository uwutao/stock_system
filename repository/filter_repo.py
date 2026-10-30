"""
文件：repository/filter_repo.py
功能：筛选结果持久化
职责：只负责把筛选结果写入 ai_filter_record 表
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text
from database.db_bak import engine


def save_filter_records(rows: list) -> int:
    """
    批量写入筛选记录
    :param rows: list[dict]，含 stock_code/ai_score/llm_analysis/min_price/max_price/max_count/use_llm
    :return: 写入行数
    """
    if not rows:
        return 0
    sql = text("""
    INSERT INTO ai_filter_record(stock_code, ai_score, llm_analysis, min_price, max_price, max_count, use_llm)
    VALUES(:stock_code, :ai_score, :llm_analysis, :min_price, :max_price, :max_count, :use_llm)
    """)
    # ✅ engine.begin() 自动事务，异常自动回滚
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)