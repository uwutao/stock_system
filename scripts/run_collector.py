import sys
import os

# 将项目根目录添加到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.stock_collector import collect_all_stocks

if __name__ == "__main__":
    collect_all_stocks()