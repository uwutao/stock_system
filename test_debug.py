import akshare as ak
import traceback

print("测试：000001 平安银行")
print("akshare 数据源：东方财富网")
print("-" * 50)

try:
    df = ak.stock_zh_a_hist(
        symbol="000001",
        period="daily",
        start_date="20250101",
        adjust="qfq"
    )

    print(f"✅ 获取成功！数据行数：{len(df)}")
    print(f"所有字段：{df.columns.tolist()}")
    print("\n预览：")
    print(df.head(3))

except Exception as e:
    print("\n❌ 失败！")
    print(f"错误类型：{type(e).__name__}")
    print(f"错误信息：{str(e)}")
    print("\n完整堆栈：")
    traceback.print_exc()