"""
文件：data/fetch_stock_basic.py
功能：采集股票基础元数据，包括股票代码、名称、上市日期、退市日期、行业信息
数据源：baostock
输出表：stock_basic
说明：仅更新基础信息，**不采集K线行情**，全量拉取，通过ON CONFLICT做增量更新，几秒跑完
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import baostock as bs
import pandas as pd
from sqlalchemy import text
from database.db import engine
#本文件用于股票基本量采集 ipo日期/行业等
def fetch_stock_basic():
    lg = bs.login()
    if lg.error_code != '0':
        raise Exception(f"baostock login fail {lg.error_msg}")
    rs = bs.query_stock_basic()
    rows = []
    while rs.error_code == '0' and rs.next():
        row = rs.get_row_data()
        code = row[0].replace("sh.","").replace("sz.","")
        name = row[1]
        ipo_date = row[2] if row[2] else None
        out_date = row[3] if row[3] else None
        typ = row[4]
        industry = row[5] if row[5] else None
        rows.append({
            "stock_code":code,"stock_name":name,"ipo_date":ipo_date,
            "out_date":out_date,"type":typ,"industry":industry
        })
    bs.logout()
    with engine.connect() as conn:
        insert_sql = text("""
        INSERT INTO stock_basic(stock_code,stock_name,ipo_date,out_date,type,industry)
        VALUES(:stock_code,:stock_name,:ipo_date,:out_date,:type,:industry)
        ON CONFLICT(stock_code) DO UPDATE SET
            stock_name=EXCLUDED.stock_name,
            ipo_date=EXCLUDED.ipo_date,
            out_date=EXCLUDED.out_date,
            type=EXCLUDED.type,
            industry=EXCLUDED.industry,
            update_time=CURRENT_TIMESTAMP;
        """)
        conn.execute(insert_sql,rows)
        conn.commit()
    print(f"✅ 写入 {len(rows)} 条股票基础信息，包含行业字段")
if __name__ == "__main__":
    fetch_stock_basic()
