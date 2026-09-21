import sys
import os
import baostock as bs

# 关键修复：把「项目根目录」加入 Python 路径
# os.path.dirname(os.path.dirname(...)) 就是从 scripts/ 往上跳一层到 stock_system/
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# 全局唯一登录
lg = bs.login()
if lg.error_code != '0':
    print("❌ baostock登录失败：", lg.error_msg)
    sys.exit(1)
else:
    print("✅ baostock登录成功！")

# 现在可以正常导入了
from data.stock_collector import collect_all_stocks

if __name__ == "__main__":
    try:
        collect_all_stocks()
    finally:
        bs.logout()
        print("\n✅ 程序退出，baostock已登出")