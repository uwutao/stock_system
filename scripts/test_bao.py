#!/usr/bin/env python3
# test_ollama.py
"""ollama连通性测试脚本，验证WSL内python可以调用Windowsollama"""
import requests

url = "http://127.0.0.1:11434/api/generate"
payload = {
    "model": "deepseek-r1:7b",
    "prompt": "一句话介绍A股",
    "stream": False
}
try:
    res = requests.post(url, json=payload, timeout=120)
    print("状态码：", res.status_code)
    print(res.json())
except requests.exceptions.Timeout:
    print("❌ 请求超时，模型推理太久，或者ollama卡住")
except Exception as e:
    print("❌ 异常：", repr(e))
