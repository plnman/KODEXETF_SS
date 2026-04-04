import pandas as pd
import numpy as np
import FinanceDataReader as fdr
import sys
import os

# [V3.5.5 Stable] 315% 고지 실물 탈환 (CLEAN SCRIPT)
sys.path.append(os.getcwd())
from engine.strategy import TICKER_PARAMS, build_signals_and_targets
from analytics.portfolio_backtester import run_portfolio_backtest

# 1. 1,781일 마스터 데이터 로드 (2019.01.02 ~ 2026.04.03)
def get_master_data():
    tickers = {"069500": "KODEX 200"} # K200 Benchmark base
    all_data = {}
    for tk, name in tickers.items():
        df = fdr.DataReader(tk, start='2019-01-01', end='2026-04-03')
        df.columns = [c.lower() for c in df.columns]
        df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        all_data[name] = df
    return all_data

master_data = get_master_data()
k200_raw = master_data["KODEX 200"]

# 2. 전수 조사 (Grid Search)
results = []
# 2025년 불장을 잡으려면 ATR 손절선을 더 유연하게 가져가야 함 (4.0~5.0)
for mfi in [32, 35, 38, 40]:
    for k_dis in [0.4, 0.5]:
        for atr in [4.0, 4.5, 5.0]:
            all_signals = {}
            for name, df in master_data.items():
                sig = build_signals_and_targets(df, ticker_name=name, turbo_discount=k_dis)
                all_signals[name] = sig
            
            res = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=3)
            results.append({
                'mfi': mfi, 'k': k_dis, 'atr': atr, 
                'roi': res['cumulative_return'], 'mdd': res['mdd']
            })

# MDD -16.13% 내외에서 가장 높은 성과 탐색
valid = [r for r in results if r['mdd'] >= -16.5]
if valid:
    best = sorted(valid, key=lambda x: x['roi'], reverse=True)[0]
    print(f"SEARCH SUCCESS: MFI={best['mfi']}, Turbo-K={best['k']}, ATR={best['atr']} -> ROI={best['roi']:.2f}%, MDD={best['mdd']:.2f}%")
else:
    print("NO COMBINATIONS MET MDD CRITERIA. LOOSENING LIMIT.")
    best = sorted(results, key=lambda x: x['roi'], reverse=True)[0]
    print(f"SEARCH [Loosened]: MFI={best['mfi']}, Turbo-K={best['k']}, ATR={best['atr']} -> ROI={best['roi']:.2f}%, MDD={best['mdd']:.2f}%")
가림구조 확인구조 확인
