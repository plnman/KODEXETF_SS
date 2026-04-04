import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from frontend.app import load_and_process_data_v3_1_2, verify_dual_source_integrity
from analytics.portfolio_backtester import run_portfolio_backtest

all_signals, is_bull_now, raw_data = load_and_process_data_v3_1_2()
port_res = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=3, use_cash_sweep=True)
current_ret = port_res.get('cumulative_return', 0.0)
print(f"app.py returns: {current_ret}")
