# # 数据库配置
# DATABASE = {
#     'host': 'localhost',
#     'port': 5432,
#     'user': 'postgres',
#     'password': 'stock123456',
#     'dbname': 'stock_data'
# }
# # Redis配置
# REDIS = {
#     'host': 'localhost',
#     'port': 6379,
#     'password': 'stock_redis_123',
#     'db': 0
# }
# #ollama配置 wsl下转连接windowsollama命令：nohup socat TCP-LISTEN:11434,fork,bind=127.0.0.1 TCP:192.168.5.3:11434 > socat_ollama.log 2>&1 &
# OLLAMA = {
#     'host': 'http://127.0.0.1:11434',
#     'model': 'deepseek-r1:7b',
#     'timeout': 120
# }
# # 数据采集配置
# COLLECTOR = {
#     'start_date': '2020-01-01',
#     'max_retries': 3,
#     'min_delay': 1,
#     'max_delay': 10
# }
# # ===================== 多周期趋势筛选配置 =====================
# TREND_CONFIG = {
#     "period_short": 40,       # 短周期：约2个月交易日
#     "period_mid": 250,        # 中周期：1年 年线
#     "period_long": 750,       # 长周期：3年

#     # 各周期打分权重，总和100；数据不足的周期权重自动置0
#     "weight_short": 25,
#     "weight_mid": 35,
#     "weight_long": 40,

#     # 原有单日量价指标总权重（降低，不再主导分数）
#     "weight_single_day": 0,

#     # 趋势判定阈值
#     "slope_weight_recent_ratio": 0.5,   # 后半段近期斜率混合权重 0~1
#     "max_drawdown_sideways": -0.25,     # 盘整最大回撤阈值 -25%
#     "max_drawdown_down": -0.30,        # 下降最大回撤阈值 -30%
# }
# # 日志配置
# LOGGING = {
#     'level': 'INFO',
#     'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     'file': 'logs/stock_system.log'
# }
# # 构建数据库连接URI
# DB_URI = f"postgresql://{DATABASE['user']}:{DATABASE['password']}@{DATABASE['host']}:{DATABASE['port']}/{DATABASE['dbname']}"
