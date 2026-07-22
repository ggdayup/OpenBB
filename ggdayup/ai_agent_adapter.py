#!/usr/bin/env python3
"""
OpenBB AI Agent Adapter (Function Calling & Tool Interface)
将 OpenBB 免费数据接口打包为适用于 LLM Agent (如 Ollama / Claude / LangChain) 的通用工具函数。
"""

import json
import logging
from typing import Dict, Any, Optional
import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OpenBBAgentAdapter")

def get_stock_quote_tool(symbol: str) -> str:
    """
    [AI Agent Tool] 获取指定美股股票的实时/最新报价与基本指标。
    
    :param symbol: 股票代码 (例如 AAPL, TSLA, NVDA, MSFT)
    :return: JSON 格式的股票价格与概览数据
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        data = {
            "symbol": symbol.upper(),
            "last_price": round(info.last_price, 2) if hasattr(info, "last_price") and info.last_price else None,
            "previous_close": round(info.previous_close, 2) if hasattr(info, "previous_close") and info.previous_close else None,
            "currency": getattr(info, "currency", "USD"),
            "market_cap": getattr(info, "market_cap", None),
            "source": "yfinance (Free)"
        }
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch quote for {symbol}: {str(e)}"})

def get_macro_interest_rate_tool() -> str:
    """
    [AI Agent Tool] 获取最新美联储有效联邦基金利率 (Fed Funds Rate) 宏观经济指标。
    
    :return: 最新美联储利率信息
    """
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
        df = pd.read_csv(url)
        df.columns = [c.upper() for c in df.columns]
        latest = df.dropna().iloc[-1]
        date_val = str(latest.get("DATE", latest.iloc[0]))
        rate_val = float(latest.get("FEDFUNDS", latest.get("VALUE", latest.iloc[1])))
        data = {
            "indicator": "Federal Funds Effective Rate",
            "date": date_val,
            "rate_percent": rate_val,
            "source": "FRED / Federal Reserve (Free)"
        }
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch macro interest rate: {str(e)}"})

# 定义供 LLM Function Calling 使用的 Tool JSON Schema
TOOLS_SCHEMA = [
    {
        "name": "get_stock_quote_tool",
        "description": "获取指定股票的最新收盘价与基本市场指标",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码，例如 AAPL, NVDA"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_macro_interest_rate_tool",
        "description": "获取最新美联储联邦基金有效利率",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

if __name__ == "__main__":
    print("=== 测试 OpenBB AI Agent 接口调用 ===")
    print("1. 测试股票行情 Tool (AAPL):")
    print(get_stock_quote_tool("AAPL"))
    print("\n2. 测试宏观利率 Tool:")
    print(get_macro_interest_rate_tool())
