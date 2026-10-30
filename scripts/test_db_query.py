#!/usr/bin/env python3
"""
test_db_query.py
数据库简易控制台查询测试脚本，无GUI，打印到终端
运行：python scripts/test_db_query.py
"""
import sys, os

# __file__ = scripts/test_db_query.py，往上跳一级得到项目根目录 stock_system
SCRIPT_FILE = os.path.abspath(__file__)
SCRIPT_DIR  = os.path.dirname(SCRIPT_FILE)
# scripts的父目录就是项目根目录
project_root = os.path.dirname(SCRIPT_DIR)

sys.path.insert(0, project_root)

from sqlalchemy import text
from database.db_bak import engine
from analysis.ai_filter import calc_stock_longterm_stats

def test_connect():
    """测试数据库连通"""
    print("=====1.测试数据库连接=====")
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1 as ok;"))
            row = res.fetchone()
            print(f"数据库连通成功! 返回:{row.ok}")
    except Exception as e:
        print(f"❌数据库连接失败:{e}")
        sys.exit(1)


def query_stock_kline_sample(stock_code="000568", limit=10):
    """查询指定股票最近N条K线，打印peTTM、pbMRQ，观察NULL情况"""
    print(f"\n=====2.查询股票 {stock_code} 最近{limit}条K线 =====")
    sql = text("""
        SELECT trade_date,close,peTTM,pbMRQ,turnover,pct_chg
        FROM daily_kline
        WHERE stock_code=:sc
        ORDER BY trade_date DESC
        LIMIT :lim
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"sc": stock_code, "lim": limit}).mappings().all()
        if not rows:
            print(f"该股票 {stock_code} 没有K线数据")
            return
        for r in rows:
            print(f"date:{r['trade_date']} close:{r['close']} peTTM:{r['peTTM']} pbMRQ:{r['pbMRQ']} turnover:{r['turnover']}")


def test_calc_long_stats(stock_code="000568"):
    """直接调用长周期指标计算函数，控制台打印结果，复现web接口逻辑"""
    print(f"\n=====3.调用calc_stock_longterm_stats 股票:{stock_code} =====")
    stats = calc_stock_longterm_stats(stock_code)
    if stats is None:
        print("返回None：历史交易日不足120条，不做分析")
        return
    for k, v in stats.items():
        print(f"{k:22s} = {v}")


def query_filter_history(limit=5):
    """查询筛选历史表ai_filter_record"""
    print(f"\n=====4.查询ai_filter_record筛选历史最近{limit}条 =====")
    sql = text("""
        SELECT id,stock_code,ai_score,filter_time,use_llm
        FROM ai_filter_record
        ORDER BY filter_time DESC LIMIT :lim
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"lim": limit}).mappings().all()
        if not rows:
            print("ai_filter_record暂无记录，需要网页执行一次筛选")
            return
        for r in rows:
            print(f"id:{r['id']} code:{r['stock_code']} score:{r['ai_score']} time:{r['filter_time']} llm:{r['use_llm']}")


if __name__ == "__main__":
    # 修改这里股票代码，测试别的股票
    TEST_STOCK = "000423"

    test_connect()
    query_stock_kline_sample(TEST_STOCK, limit=10)
    test_calc_long_stats(TEST_STOCK)
    query_filter_history(limit=5)

    print("\n✅全部测试执行完毕")
