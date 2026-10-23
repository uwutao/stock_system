from flask import Flask, render_template, request, jsonify
import pandas as pd
from database.db import execute_sql
# 导入你的AI选股函数（下面会写）
from analysis.ai_filter import ai_stock_filter

app = Flask(__name__)

# 首页：AI筛选面板
@app.route('/')
def index():
    return render_template("ai_analysis.html")

# AI筛选接口，POST接收参数
@app.route("/api/run_filter", methods=["POST"])
def run_filter():
    data = request.get_json()
    # 拿到前端传过来的筛选参数
    min_price = data.get("min_price", 0)
    max_price = data.get("max_price", 1000)
    max_count = data.get("max_count", 20)
    use_llm = data.get("use_llm", False)

    # 调用AI选股逻辑，从PG数据库读取K线，计算打分
    result_df = ai_stock_filter(min_price, max_price, max_count, use_llm)
    res_list = result_df.to_dict("records")
    return jsonify({"code":0, "data": res_list})

# 个股详情接口
@app.route("/api/stock_detail/<code>")
def stock_detail(code):
    # 查询单只股票K线、指标、AI分析文本
    return jsonify({})

if __name__ == '__main__':
    # WSL访问：http://127.0.0.1:5000
    app.run(host="0.0.0.0", port=5000, debug=True)
