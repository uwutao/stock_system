import baostock as bs
import pandas as pd
import time
import random

print("✅ baostock 数据源测试（含成交量/换手率，无反爬限制）")
print("-" * 50)

# 登录baostock（免费接口，无需注册）
lg = bs.login()
print('登录状态码：', lg.error_code)
print('登录信息：', lg.error_msg)

# 配置股票代码（注意格式：深市sz.xxxxxx，沪市sh.xxxxxx）
stock_code = "sz.000001"  # 平安银行（深市）
start_date = "2025-01-01"
end_date = "2025-01-05"

try:
    # 随机延迟，模拟人类操作（1-2秒，极低频率）
    time.sleep(random.uniform(1, 2))
    
    # 获取日线数据（包含你需要的所有字段）
    rs = bs.query_history_k_data_plus(
        stock_code,
        "date,open,high,low,close,volume,amount,turn,pctChg",
        start_date=start_date,
        end_date=end_date,
        frequency="d",  # 日线
        adjustflag="3"  # 前复权（和东方财富的qfq一致）
    )
    
    # 转换为DataFrame（和akshare格式一致）
    data_list = []
    while (rs.error_code == '0') & rs.next():
        data_list.append(rs.get_row_data())
    df = pd.DataFrame(data_list, columns=rs.fields)
    
    print("✅ 获取成功！数据行数：", len(df))
    print("所有字段：", df.columns.tolist())
    print("\n数据预览：")
    print(df.head())

except Exception as e:
    print("❌ 获取失败！")
    print("错误信息：", e)

# 登出baostock
bs.logout()