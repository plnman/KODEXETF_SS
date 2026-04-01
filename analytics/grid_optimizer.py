import pandas as pd
import yfinance as yf
import sys
import os
import itertools
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.backtester import run_vectorized_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

def optimize_parameters():
    print("🔥 [전 종목 1:1 파라미터 최적화(Grid Search) 가동 시작]")
    print("목표: 종목별 B&H(단순 존버) 대비 수익률(Alpha)을 극대화하는 최고의 Parameter 조합 탐색\n")
    
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2019-01-01", progress=False)
    
    clean_data_dict = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, raw_ticker) in data.columns:
                df_clean[col.lower()] = data[(col, raw_ticker)]
            elif col in data.columns and len(tickers_list) == 1:
                df_clean[col.lower()] = data[col]
                
        df_clean = df_clean.dropna().reset_index()
        if df_clean.empty: continue
        
        df_clean['date'] = pd.to_datetime(df_clean['Date']).dt.strftime('%Y-%m-%d')
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        df_clean = df_clean.dropna().reset_index(drop=True)
        clean_data_dict[name] = df_clean

    # [V3.1] 시장 레짐 판독 (KODEX 200 기준)
    k200_df = clean_data_dict['KODEX 200']
    k200_signals = build_signals_and_targets(k200_df.copy(), ticker_name="KODEX 200")
    regime_series = get_market_regime(k200_signals)
    # 날짜별 불장/안정장 매핑 딕셔너리 생성
    regime_map = regime_series.to_dict() # Index가 original df와 동일하므로 바로 매핑 가능
    regime_vector_map = {}
    for name, df in clean_data_dict.items():
        # 각 종목의 인덱스에 맞춰 레짐 벡터 생성
        regime_vector_map[name] = regime_series.reindex(df.index).fillna(False)

    # 그리드 셋업: (K: 넓은 범위, MFI: 40~70 범위, ADX: 15~25 범위)
    k_values = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    mfi_values = [40, 50, 60, 65]
    adx_values = [15, 20, 25]
    grid = list(itertools.product(k_values, mfi_values, adx_values))
    
    final_optimal_dict = {}
    
    for name, df_clean in clean_data_dict.items():
        first_price = df_clean['open'].iloc[0]
        last_price = df_clean['close'].iloc[-1]
        bnh_rate = ((last_price / first_price) - 1) * 100
        
        best_alpha = -9999
        best_combo = None
        best_winrate = 0
        best_total = 0
        
        for k, mfi, adx in grid:
            overrides = {"k": k, "mfi": mfi, "adx_threshold": adx}
            # V3.1: 레짐 벡터를 전달하여 하이브리드 시뮬레이션
            regime_v = regime_vector_map[name]
            signals = build_signals_and_targets(df_clean, ticker_name=name, overrides=overrides, is_bull_market=regime_v)
            res = run_vectorized_backtest(signals, initial_capital=5000000)
            
            if "error" not in res:
                ret_rate = ((res['final_capital'] / 5000000) - 1) * 100
                alpha = ret_rate - bnh_rate
                
                # 최고 누적수익(Alpha)이 승리, 단 승률이 너무 처참한 경우는 필터링 가능
                if alpha > best_alpha:
                    best_alpha = alpha
                    best_combo = overrides
                    best_winrate = res.get('win_rate', 0)
                    best_total = ret_rate
                    
        print(f"[{name}] 최적 파라미터 조합 발견: {best_combo}")
        print(f" -> 알고리즘 수익: {best_total:,.2f}% | B&H 존버 수익률: {bnh_rate:,.2f}% | 획득 Alpha: +{best_alpha:,.2f}% | 알고리즘 승률: {best_winrate}%\n")
        final_optimal_dict[name] = best_combo
        
    print("\n✅ [복사-붙여넣기용 최종 TICKER_PARAMS 딕셔너리]")
    print("TICKER_PARAMS = {")
    for name, params in final_optimal_dict.items():
        print(f'    "{name}": {params},')
    print("}")

if __name__ == "__main__":
    optimize_parameters()
