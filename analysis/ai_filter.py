import pandas as pd
from database.db import execute_sql

def ai_stock_filter(min_price, max_price, max_count=20, use_llm=False):
    """
    AI量化打分选股，从数据库读取日线K线，计算指标，打分筛选
    """
    # 从你的k线表读取所有股票最新数据，这里简化示例
    sql = """
    SELECT code, name, close, volume, industry FROM stock_daily
    WHERE close >= %s AND close <= %s
    """
    df = execute_sql(sql, (min_price, max_price), return_df=True)

    # 这里写打分逻辑，示例规则：
    def calc_score(row):
        score = 0
        # 示例规则，你后续可以扩充成你的策略
        if row["close"] > row["ma20"]: score += 30
        if row["volume"] > row["vol_5avg"]: score +=25
        return min(score,100)

    # 计算得分，过滤、排序，取topN
    df["ai_score"] = df.apply(calc_score, axis=1)
    df = df[df["ai_score"]>50].sort_values("ai_score", ascending=False).head(max_count)
    return df
