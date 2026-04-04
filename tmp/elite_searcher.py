import os
import sys
import io
import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf

# UTF-8 출력 강제 (Windows 대응)
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

# Add current directory to sys.path
sys.path.append(os.getcwd())

from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def greedy_portfolio_optimization():
    print("🚀 [Greedy Optimizer] 22종목 하이브리드 최적화 엔진 가동...")
    
    TARGET_ETFS = {
        "069500.KS": "KODEX 200", "226490.KS": "KODEX 코스닥150", 
        "091160.KS": "KODEX 반도체", "091170.KS": "KODEX 은행", 
        "091180.KS": "KODEX 자동차", "305720.KS": "KODEX 2차전지산업", 
        "117700.KS": "KODEX 건설", "091220.KS": "KODEX 금융", 
        "102970.KS": "KODEX 기계장비", "117680.KS": "KODEX 철강",
        "379800.KS": "KODEX 미국S&P500TR", "367380.KS": "KODEX 미국나스닥100TR", 
        "314250.KS": "KODEX 미국FANG플러스(H)", "315270.KS": "KODEX 미국산업재(합성)", 
        "251350.KS": "KODEX 선진국MSCI World", "475380.KS": "KODEX 글로벌AI인프라", 
        "453850.KS": "KODEX 인도Nifty50", "465610.KS": "KODEX 미국반도체MV", 
        "461580.KS": "KODEX 미국배당프리미엄액티브", "480600.KS": "KODEX K방산TOP10", 
        "244580.KS": "KODEX 바이오", "315930.KS": "KODEX Top5PlusTR"
    }

    # 1. 데이터 로딩 (app.py 로직 재현)
    start_date = "2019-01-01"
    raw_dfs = {}
    print("📥 데이터 다운로드 중...")
    tickers = list(TARGET_ETFS.keys())
    data = yf.download(tickers, start=start_date, progress=False)
    
    for tk, name in TARGET_ETFS.items():
        df = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, tk) in data.columns:
                df[col] = data[(col, tk)]
        df = df.dropna().reset_index()
        df.rename(columns={'Date': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
        if df.empty: continue
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        raw_dfs[name] = df

    # 2. 레짐 판독 (K200 기준)
    k200_raw = raw_dfs["KODEX 200"]
    k200_sigs = build_signals_and_targets(k200_raw, "KODEX 200")
    regime_series = get_market_regime(k200_sigs)

    # 3. 튜닝 파라미터 초기화 (V3.5.0 Baseline)
    params = {
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
        "KODEX 미국S&P500TR": {'k': 0.7, 'mfi': 40, 'adx_threshold': 15},
        "KODEX 미국나스닥100TR": {'k': 0.5, 'mfi': 50, 'adx_threshold': 15},
        "KODEX 미국FANG플러스(H)": {'k': 0.4, 'mfi': 60, 'adx_threshold': 20},
        "KODEX 미국산업재(합성)": {'k': 0.5, 'mfi': 50, 'adx_threshold': 15},
        "KODEX 선진국MSCI World": {'k': 0.6, 'mfi': 40, 'adx_threshold': 15},
        "KODEX 글로벌AI인프라": {'k': 0.3, 'mfi': 55, 'adx_threshold': 20},
        "KODEX 인도Nifty50": {'k': 0.6, 'mfi': 50, 'adx_threshold': 15},
        "KODEX 미국반도체MV": {'k': 0.3, 'mfi': 60, 'adx_threshold': 20},
        "KODEX 미국배당프리미엄액티브": {'k': 0.8, 'mfi': 40, 'adx_threshold': 15},
        "KODEX K방산TOP10": {'k': 0.3, 'mfi': 60, 'adx_threshold': 20},
        "KODEX 바이오": {'k': 0.2, 'mfi': 60, 'adx_threshold': 15},
        "KODEX Top5PlusTR": {'k': 0.5, 'mfi': 50, 'adx_threshold': 15}
    }

    NEW_12 = [ "KODEX 미국S&P500TR", "KODEX 미국나스닥100TR", "KODEX 미국FANG플러스(H)", "KODEX 미국산업재(합성)", "KODEX 선진국MSCI World", "KODEX 글로벌AI인프라", "KODEX 인도Nifty50", "KODEX 미국반도체MV", "KODEX 미국배당프리미엄액티브", "KODEX K방산TOP10", "KODEX 바이오", "KODEX Top5PlusTR" ]

    def evaluate(p):
        all_sigs = {}
        for name, df in raw_dfs.items():
            # Sync logic (app.py 103)
            df_sync = df.set_index('date').reindex(k200_raw.set_index('date').index).reset_index().ffill().fillna(0)
            df_sync = df_sync.drop_duplicates(subset=['date'])
            sigs = build_signals_and_targets(df_sync, name, overrides=p[name], is_bull_market=regime_series)
            all_sigs[name] = sigs
        res = run_portfolio_backtest(all_sigs, 50000000.0, 3, True)
        return res['cumulative_return']

    best_ret = evaluate(params)
    print(f"🎬 Initial Return: {best_ret:.2f}%")

    # Greedy loop
    for ticker_name in NEW_12:
        print(f"🔄 Optimizing {ticker_name}...")
        original_k = params[ticker_name]['k']
        local_best_k = original_k
        
        for k_test in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            params[ticker_name]['k'] = k_test
            curr_ret = evaluate(params)
            if curr_ret > best_ret:
                best_ret = curr_ret
                local_best_k = k_test
                print(f"✨ Found improved K={k_test} for {ticker_name} -> {best_ret:.2f}%")
        
        params[ticker_name]['k'] = local_best_k

    print("\n" + "="*60)
    print(f"🏆 Final Optimized Return: {best_ret:.2f}%")
    print("="*60)
    print("📋 Optimized TICKER_PARAMS:")
    for tk, val in params.items():
        print(f"    '{tk}': {val},")

if __name__ == "__main__":
    greedy_portfolio_optimization()
