"""
文件：database/db.py
功能：数据库连接、会话、表初始化，定义所有DDL
"""
import sys
import os
# 往上跳一层，拿到项目根目录，加入Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config.settings import DB_URI
import logging
# 配置日志
logger = logging.getLogger(__name__)
# 创建数据库引擎
engine = create_engine(
    DB_URI,
    pool_pre_ping=True,
    pool_size=6,       # 大于线程数4
    max_overflow=4,
    pool_recycle=180
    )
# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def execute_sql(sql, params=None):
    """执行SQL语句"""
    with engine.connect() as conn:
        if params:
            result = conn.execute(text(sql), params)
        else:
            result = conn.execute(text(sql))
        conn.commit()
        return result

def init_database():
    """初始化数据库表结构"""
    logger.info("正在初始化数据库表结构...")

    # 日线数据表，新增估值字段 peTTM pbMRQ psTTM pcfNcfTTM isST
    execute_sql("""
        CREATE TABLE IF NOT EXISTS daily_kline (
            id SERIAL PRIMARY KEY,
            stock_code VARCHAR(10) NOT NULL,
            stock_name VARCHAR(50) NOT NULL,
            trade_date DATE NOT NULL,
            open NUMERIC(10,2),
            close NUMERIC(10,2),
            high NUMERIC(10,2),
            low NUMERIC(10,2),
            preclose NUMERIC(10,2),
            volume BIGINT,
            amount NUMERIC(18,2),
            amplitude NUMERIC(5,2),
            pct_chg NUMERIC(5,2),
            change_amount NUMERIC(10,2),
            turnover NUMERIC(5,2),
            peTTM NUMERIC(12,4),
            pbMRQ NUMERIC(12,4),
            psTTM NUMERIC(12,4),
            pcfNcfTTM NUMERIC(12,4),
            isST VARCHAR(2),
            UNIQUE(stock_code, trade_date)
        );
        -- 已经存在表就追加新列，防止重复建表报错
        ALTER TABLE daily_kline ADD COLUMN IF NOT EXISTS peTTM NUMERIC(12,4);
        ALTER TABLE daily_kline ADD COLUMN IF NOT EXISTS pbMRQ NUMERIC(12,4);
        ALTER TABLE daily_kline ADD COLUMN IF NOT EXISTS psTTM NUMERIC(12,4);
        ALTER TABLE daily_kline ADD COLUMN IF NOT EXISTS pcfNcfTTM NUMERIC(12,4);
        ALTER TABLE daily_kline ADD COLUMN IF NOT EXISTS isST VARCHAR(2);

        CREATE INDEX IF NOT EXISTS idx_daily_kline_stock_code ON daily_kline(stock_code);
        CREATE INDEX IF NOT EXISTS idx_daily_kline_trade_date ON daily_kline(trade_date);
    """)

    # 股票基础信息表(行业、上市日期)
    execute_sql("""
        CREATE TABLE IF NOT EXISTS stock_basic (
            stock_code VARCHAR(10) PRIMARY KEY,
            stock_name VARCHAR(50),
            ipo_date DATE,
            out_date DATE,
            type VARCHAR(10),
            industry VARCHAR(64),
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # AI筛选历史记录表
    execute_sql("""
    CREATE TABLE IF NOT EXISTS ai_filter_record (
        id SERIAL PRIMARY KEY,
        stock_code VARCHAR(10) NOT NULL,
        filter_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ai_score INTEGER,
        llm_analysis TEXT,
        min_price NUMERIC,
        max_price NUMERIC,
        max_count INTEGER,
        use_llm BOOLEAN,
        FOREIGN KEY (stock_code) REFERENCES stock_basic(stock_code) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ai_filter_time ON ai_filter_record(filter_time);
    CREATE INDEX IF NOT EXISTS idx_ai_filter_code ON ai_filter_record(stock_code);
    """)

    # 新闻表，原样不动
    execute_sql("""
        CREATE TABLE IF NOT EXISTS stock_news (
            id SERIAL PRIMARY KEY,
            stock_code VARCHAR(10) NOT NULL,
            title VARCHAR(255) NOT NULL,
            content TEXT,
            source VARCHAR(50),
            publish_time TIMESTAMP,
            url VARCHAR(512) UNIQUE,
            sentiment_score NUMERIC(3,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_stock_news_stock_code ON stock_news(stock_code);
        CREATE INDEX IF NOT EXISTS idx_stock_news_publish_time ON stock_news(publish_time);
    """)
    logger.info("数据库表结构初始化完成！")
