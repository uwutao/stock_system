"""
文件：data/fetch_stock_basic.py
功能：采集股票基础元数据（代码、名称、上市/退市日期、type、行业）
数据源：baostock
输出表：stock_basic
✅ 修复：行业字段改为调用 query_stock_industry() 单独拉取
   （query_stock_basic 返回的第6列是 status，不是 industry；原代码存错）
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import baostock as bs
from sqlalchemy import text
from database.db_bak import engine


def fetch_stock_basic():
    """
    全量拉取股票基础信息 + 行业信息，通过 ON CONFLICT 做增量更新
    行业来源：bs.query_stock_industry() 返回 updateDate / code / code_name / industry / industryClassification
    """
    lg = bs.login()
    if lg.error_code != '0':
        raise Exception(f"baostock login fail {lg.error_msg}")

    # 1) 基础信息
    rs = bs.query_stock_basic()
    rows = []
    while rs.error_code == '0' and rs.next():
        row = rs.get_row_data()
        code = row[0].replace("sh.", "").replace("sz.", "")
        rows.append({
            "stock_code": code,
            "stock_name": row[1],
            "ipo_date": row[2] if row[2] else None,
            "out_date": row[3] if row[3] else None,
            "type": row[4],
        })

    # 2) 行业映射（单独接口）
    rs_ind = bs.query_stock_industry()
    industry_map = {}
    while rs_ind.error_code == '0' and rs_ind.next():
        r = rs_ind.get_row_data()
        pure_code = r[1].replace("sh.", "").replace("sz.", "")
        industry_map[pure_code] = r[3] if r[3] else None

    bs.logout()

    # 3) 合并行业
    for r in rows:
        r["industry"] = industry_map.get(r["stock_code"])

    # 4) 入库（engine.begin() 自动事务）
    with engine.begin() as conn:
        conn.execute(text("""
        INSERT INTO stock_basic(stock_code, stock_name, ipo_date, out_date, type, industry)
        VALUES(:stock_code, :stock_name, :ipo_date, :out_date, :type, :industry)
        ON CONFLICT(stock_code) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            ipo_date = EXCLUDED.ipo_date,
            out_date = EXCLUDED.out_date,
            type = EXCLUDED.type,
            industry = EXCLUDED.industry,
            update_time = CURRENT_TIMESTAMP;
        """), rows)

    print(f"✅ 写入 {len(rows)} 条股票基础信息，行业已对齐 {len(industry_map)} 条")


if __name__ == "__main__":
    fetch_stock_basic()