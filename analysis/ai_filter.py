"""
文件：analysis/ai_filter.py
功能：兼容壳（薄封装层）
说明：
  本文件已解耦，内部只做转发，不承载业务逻辑
  保留本文件是为了让 app.py 等旧调用方零改动
  新代码请直接调用 services / repository / analysis 下对应的模块
"""
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 纯计算：趋势
from analysis.trend import (
    calc_trend_single_series,
    calc_multi_period_trend_batch,
    calc_multi_period_trend_from_df,
)
# 长周期统计
from analysis.longterm_stats import calc_stock_longterm_stats
# LLM 调用
from services.llm_client import (
    call_llm_stock_analysis,
    call_llm_single_deep_analysis,
    call_llm_longterm_analysis,
)
# 编排：筛选 + LLM + 写库
from services.analysis_service import run_filter_with_analysis
# 数据查询
from repository.kline_repo import get_single_stock_info


def ai_stock_filter(min_price, max_price, max_count=20, use_llm=False):
    """
    【兼容旧接口】批量股票筛选 + 可选 LLM 分析 + 记录写库
    实际实现已拆到：
      - services/filter_service.py（纯筛选）
      - services/analysis_service.py（编排）
      - services/llm_client.py（LLM）
      - repository/*（数据访问）
    :return: DataFrame，字段同旧版（code/name/close/.../ai_total_score/llm_analysis）
    """
    return run_filter_with_analysis(min_price, max_price, max_count, use_llm)