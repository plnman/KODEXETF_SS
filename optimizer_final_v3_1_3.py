import pandas as pd
import yfinance as yf
import numpy as np
import sys
import os

# 현재 경로 추가
sys.path.append(os.getcwd())
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

def optimize():
    # 1. 데이터 로드 (시뮬레이션용)
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2019-01-01", progress=False)
    
    k200_raw = pd.DataFrame()
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        k200_raw[col.lower()] = data[(col, "069500.KS")]
    k200_raw = k200_raw.dropna().reset_index()
    k200_raw['date'] = k200_raw['Date'].dt.strftime('%Y-%m-%d')
    df_upper_k2 = k200_raw.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
    k200_raw['mfi'] = calculate_mfi(df_upper_k2)
    k200_raw['intraday_intensity'] = calculate_intraday_intensity(df_upper_k2)
    k200_signals = build_signals_and_targets(k200_raw, ticker_name="KODEX 200")
    regime_series = get_market_regime(k200_signals)

    common_dates = data.index
    cleaned_data_map = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = pd.DataFrame(index=common_dates)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df_clean[col.lower()] = data[(col, raw_ticker)]
        df_clean = df_clean.ffill().dropna().reset_index()
        df_clean.rename(columns={'Date': 'date'}, inplace=True)
        df_clean['date'] = df_clean['date'].dt.strftime('%Y-%m-%d')
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        cleaned_data_map[name] = df_clean

    # 집중형을 위한 그리드 탐색
    best_cagr = -999
    best_params = {}
    
    # 3종목 집중 투자는 K값을 중립 이하로 하고 ADX 필터를 강화
    for k in [0.2, 0.4, 0.6]:
        for mfi_thr in [45, 55, 65]:
            for adx_thr in [15, 20]:
                all_signals = {}
                for name, df in cleaned_data_map.items():
                    overrides = {"k": k, "mfi": mfi_thr, "adx_threshold": adx_thr}
                    all_signals[name] = build_signals_and_targets(df, ticker_name=name, overrides=overrides, is_bull_market=regime_series)
                
                res = run_portfolio_backtest(all_signals, max_tickers=3, weight_per_ticker=0.33)
                if res['cagr'] > best_cagr:
                    best_cagr = res['cagr']
                    best_params = {'k': k, 'mfi': mfi_thr, 'adx': adx_thr, 'mdd': res['mdd']}

    # 각 종목별 최적 K-Value 미세 조정 시뮬레이션 결과 반영 (예시 - 최상단 결과가 보편적 최적)
    print(f"RESULT: {best_params['k']},{best_params['mfi']},{best_params['adx']},{best_cagr:.2f},{best_params['mdd']:.2f}")

if __name__ == "__main__":
    optimize()
