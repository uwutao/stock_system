import akshare as ak
import time
import random
import requests
from requests.utils import default_headers

# ========== 关键：修改requests默认请求头，模拟Chrome浏览器 ==========
# 给所有requests请求（包括akshare的）带上真实的User-Agent和Referer
headers = default_headers()
headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
headers["Referer"] = "https://quote.eastmoney.com/"

# 给requests设置默认headers
requests.session().headers.update(headers)

print("✅ 已设置真实浏览器请求头，开始测试...")
print("-" * 50)

# 重试次数和延迟
max_retries = 5
retry_delay = 2

for attempt in range(max_retries):
    try:
        # 随机延迟，模拟人类操作（2-4秒，拉低频率）
        time.sleep(random.uniform(2, 4))
        
        # 测试东方财富接口（平安银行 000001）
        df = ak.stock_zh_a_hist(
            symbol="000001",
            period="daily",
            start_date="20250101",
            end_date="20250105",
            adjust="qfq"
        )
        
        print("✅ 获取成功！数据行数：", len(df))
        print("所有字段：", df.columns.tolist())
        print("\n数据预览：")
        print(df.head())
        break
        
    except Exception as e:
        print(f"⚠️ 第 {attempt+1} 次尝试失败: {e}")
        if attempt < max_retries - 1:
            print(f"等待 {retry_delay} 秒后重试...")
            time.sleep(retry_delay)
            retry_delay *= 1.5  # 指数退避，越失败延迟越长
        else:
            print("❌ 多次尝试均失败，东方财富反爬限制太严了")
            print("👉 建议直接切换到新浪财经数据源，不用折腾反爬")