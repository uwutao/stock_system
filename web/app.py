from flask import Flask, render_template, request, jsonify
import pandas as pd
import sys,os
# 关键：把项目根目录加入python搜索路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
from database.db_bak import execute_sql
# 导入全部函数：新增calc_stock_longterm_stats、call_llm_longterm_analysis
from analysis.ai_filter import (
    ai_stock_filter,
    get_single_stock_info,
    call_llm_single_deep_analysis,
    calc_stock_longterm_stats,
    call_llm_longterm_analysis
)
import requests
from config.settings import OLLAMA

app = Flask(__name__)

@app.route('/')
def index():
    """首页：渲染ai_analysis.html前端页面"""
    return render_template("ai_analysis.html")


@app.route("/api/run_filter", methods=["POST"])
def run_filter():
    """
    批量筛选接口，对应前端【执行筛选】按钮
    入参json：min_price,max_price,max_count,use_llm
    返回：筛选后的股票列表json
    """
    try:
        data = request.get_json()
        min_price = data.get("min_price", 0)
        max_price = data.get("max_price", 1000)
        max_count = data.get("max_count", 20)
        use_llm = data.get("use_llm", False)
        result_df = ai_stock_filter(min_price, max_price, max_count, use_llm)
        res_list = result_df.to_dict("records")
        return jsonify({"code":0, "data": res_list})
    except Exception as e:
        return jsonify({"code":-1,"msg":str(e)})


@app.route("/api/single_stock_analyse",methods=["POST"])
def single_stock_analyse():
    """
    ✨【新版长周期深度分析接口】前端【深度K线分析】按钮调用
    """
    import traceback
    try:
        body = request.get_json()
        stock_code = body.get("stock_code","")
        if not stock_code:
            return jsonify({"code":-1,"msg":"缺少股票代码"})
        stats = calc_stock_longterm_stats(stock_code)
        if stats is None:
            return jsonify({"code":-1,"msg":"该股票历史K线数据不足，无法做长周期分析，需要至少120个交易日数据"})
        ret = call_llm_longterm_analysis(stats)
        return jsonify({"code":0,"data":{"stock_stats":stats,"analysis":ret}})
    except Exception as e:
        err_stack = traceback.format_exc()
        print("\n========深度分析接口异常TRACEBACK========")
        print(err_stack)
        print("========================================\n")
        return jsonify({"code":-1,"msg":str(e)})


@app.route("/api/chat_llm",methods=["POST"])
def chat_llm():
    """通用自由聊天窗口接口，右下角悬浮对话框调用，直接透传prompt给ollama"""
    try:
        body = request.get_json()
        user_msg = body.get("msg","")
        payload = {
            "model":OLLAMA["model"],
            "prompt":user_msg,
            "stream":False
        }
        resp = requests.post(OLLAMA["host"]+"/api/generate",json=payload,timeout=OLLAMA["timeout"])
        j = resp.json()
        return jsonify({
            "code":0,
            "data":{
                "think":j.get("thinking",""),
                "content":j.get("response","")
            }
        })
    except Exception as e:
        return jsonify({"code":-1,"msg":str(e)})


@app.route("/api/stock_detail/<code>")
def stock_detail(code):
    """预留个股详情接口，暂未实现业务逻辑"""
    return jsonify({"code":0,"data":{"stock_code":code}})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
