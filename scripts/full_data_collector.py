import akshare as ak
import pandas as pd
from sqlalchemy import create_engine, text
import time
import random
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests

# 数据库连接配置
DB_URI = 'postgresql://postgres:stock123456@localhost:5432/stock_data'
engine = create_engine(DB_URI, pool_pre_ping=True)

# 重试机制：遇到网络错误最多重试5次，指数退避等待
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type((requests.exceptions.RequestException, ConnectionResetError))
)
def get_stock_kline(stock_code, start_date="20200101"):
    return ak.stock_zh_a_hist(
        symbol=stock_code, 
        period="daily", 
        start_date=start_date, 
        adjust="qfq"
    )

def init_database():
    """初始化数据库表结构"""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_kline (
                id SERIAL PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL,
                stock_name VARCHAR(50) NOT NULL,
                trade_date DATE NOT NULL,
                open NUMERIC(10,2),
                close NUMERIC(10,2),
                high NUMERIC(10,2),
                low NUMERIC(10,2),
                volume BIGINT,
                amount NUMERIC(18,2),
                amplitude NUMERIC(5,2),
                pct_chg NUMERIC(5,2),
                change_amount NUMERIC(10,2),
                turnover NUMERIC(5,2),
                UNIQUE(stock_code, trade_date)
            );
            CREATE INDEX IF NOT EXISTS idx_daily_kline_stock_code ON daily_kline(stock_code);
            CREATE INDEX IF NOT EXISTS idx_daily_kline_trade_date ON daily_kline(trade_date);
        """))
        conn.commit()

def get_collected_stocks():
    """获取已经采集过的股票列表"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT stock_code FROM daily_kline"))
        return {row[0] for row in result.fetchall()}

def save_daily_kline(stock_code, stock_name, start_date="20200101"):
    try:
        df = get_stock_kline(stock_code, start_date)
        
        if df.empty:
            return False

        # 数据清洗和重命名
        df.rename(columns={
            '日期': 'trade_date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '振幅': 'amplitude', '涨跌幅': 'pct_chg',
            '涨跌额': 'change_amount', '换手率': 'turnover'
        }, inplace=True)
        
        df['stock_code'] = stock_code
        df['stock_name'] = stock_name
        
        # 批量存入数据库，冲突时忽略
        df.to_sql(
            'daily_kline', 
            engine, 
            if_exists='append', 
            index=False, 
            method='multi',
            chunksize=1000,
            dtype={}
        )
        return True

    except Exception as e:
        print(f"\n❌ 处理失败 {stock_code} {stock_name}: {str(e)}")
        return False

if __name__ == "__main__":
    # 安装必要的依赖
    import subprocess
    subprocess.run(["pip", "install", "tqdm", "tenacity", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
    
    # 初始化数据库
    print("正在初始化数据库...")
    init_database()
    
    # 获取所有A股股票
    print("正在获取A股股票列表...")
    stock_df = ak.stock_info_a_code_name()
    total_stocks = len(stock_df)
    print(f"共获取到 {total_stocks} 只A股股票")
    
    # 获取已经采集过的股票
    collected_stocks = get_collected_stocks()
    print(f"已经采集过 {len(collected_stocks)} 只股票")
    
    # 筛选出还未采集的股票
    remaining_stocks = stock_df[~stock_df['code'].isin(collected_stocks)]
    remaining_count = len(remaining_stocks)
    print(f"剩余 {remaining_count} 只股票待采集\n")
    
    if remaining_count == 0:
        print("🎉 所有股票数据已经采集完成！")
        exit()
    
    # 开始采集
    success_count = 0
    failed_count = 0
    
    pbar = tqdm(remaining_stocks.iterrows(), total=remaining_count, desc="采集进度")
    
    for index, row in pbar:
        code = row['code']
        name = row['name']
        
        if save_daily_kline(code, name):
            success_count += 1
        else:
            failed_count += 1
        
        # 更新进度条描述
        pbar.set_postfix({
            '成功': success_count,
            '失败': failed_count
        })
        
        # 随机延迟0.8-2秒，防止被限流
        time.sleep(random.uniform(0.8, 2.0))
    
    print(f"\n✅ 采集完成！成功: {success_count}, 失败: {failed_count}")
    print(f"总共已采集: {len(collected_stocks) + success_count} / {total_stocks} 只股票")
    
    if failed_count > 0:
        print("\n💡 提示：失败的股票会在下次运行时自动重新采集")