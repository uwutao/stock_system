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

# Ollama配置（连接Windows上的Ollama服务）
OLLAMA = {
    'host': 'http://host.docker.internal:11434',
    'model': 'deepseek-r1:7b',
    'timeout': 120
}

# 数据采集配置
COLLECTOR = {
    'start_date': '20200101',
    'max_retries': 5,
    'min_delay': 0.8,
    'max_delay': 2.0
}

# 日志配置
LOGGING = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'logs/stock_system.log'
}

# 构建数据库连接URI
DB_URI = f"postgresql://{DATABASE['user']}:{DATABASE['password']}@{DATABASE['host']}:{DATABASE['port']}/{DATABASE['dbname']}"