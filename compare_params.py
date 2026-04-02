import pandas as pd
import yfinance as yf
import sys
import os

# 현재 경로 추가
sys.path.append(os.getcwd())
from engine.strategy import build_signals_and_targets
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

# 이전 파라미터 셋 (Legacy)
PREV_PARAMS = {
    "KODEX 200": {'k': 0.7, 'mfi': 40, 'adx_threshold': 15},
    "KODEX 코스닥150": {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 반도체": {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 은행": {'k': 0.7, 'mfi': 65, 'adx_threshold': 20},
    "KODEX 자동차": {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 2차전지산업": {'k': 0.3, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 건설": {'k': 0.4, 'mfi': 60, 'adx_threshold': 15},
    "KODEX 금융": {'k': 0.5, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 기계장비": {'k': 0.7, 'mfi': 65, 'adx_threshold': 15},
    "KODEX 철강": {'k': 0.3, 'mfi': 40, 'adx_threshold': 15},
}

# 현재 최적화 파라미터 셋 (V3.1.3 Unified)
CURR_PARAMS_VAL = {'k': 0.4, 'mfi': 55, 'adx_threshold': 15}

def run_compare():
    # 데이터 로드
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2019-01-01", progress=False)
    
    cleaned_data_map = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = data.xs(raw_ticker, level=1, axis=1).ffill().dropna().reset_index()
        df_clean.rename(columns={'Date': 'date'}, inplace=True)
        df_clean.columns = [c.lower() for c in df_clean.columns]
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        cleaned_data_map[name] = df_clean

    # [1] 이전 파라미터 백테스트
    signals_prev = {}
    for name, df in cleaned_data_map.items():
        p = PREV_PARAMS[name]
        signals_prev[name] = build_signals_and_targets(df, ticker_name=name, overrides=p)
    res_prev = run_portfolio_backtest(signals_prev, max_tickers=3, weight_per_ticker=0.33)

    # [2] 현재 파라미터 백테스트
    signals_curr = {}
    for name, df in cleaned_data_map.items():
        signals_curr[name] = build_signals_and_targets(df, ticker_name=name, overrides=CURR_PARAMS_VAL)
    res_curr = run_portfolio_backtest(signals_curr, max_tickers=3, weight_per_ticker=0.33)

    print(f"PREV|{res_prev['cagr']}|{res_prev['mdd']}|{res_prev['final_capital']}")
    print(f"CURR|{res_curr['cagr']}|{res_curr['mdd']}|{res_curr['final_capital']}")

if __name__ == "__main__":
    run_compare()
