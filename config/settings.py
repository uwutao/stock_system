# 数据库配置
DATABASE = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',
    'password': 'stock123456',
    'dbname': 'stock_data'
}

# Redis配置
REDIS = {
    'host': 'localhost',
    'port': 6379,
    'password': 'stock_redis_123',
    'db': 0
}
#ollama配置 wsl下转连接windowsollama命令：nohup socat TCP-LISTEN:11434,fork,bind=127.0.0.1 TCP:192.168.5.3:11434 > socat_ollama.log 2>&1 &
OLLAMA = {
    'host': 'http://127.0.0.1:11434',
    'model': 'deepseek-r1:7b',
    'timeout': 120
}


# 数据采集配置
COLLECTOR = {
    'start_date': '2020-01-01',
    'max_retries': 3,
    'min_delay': 1,
    'max_delay': 10
}

# 日志配置
LOGGING = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'logs/stock_system.log'
}

# 构建数据库连接URI
DB_URI = f"postgresql://{DATABASE['user']}:{DATABASE['password']}@{DATABASE['host']}:{DATABASE['port']}/{DATABASE['dbname']}"