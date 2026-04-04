import pandas as pd
import numpy as np
import sys
import os
import FinanceDataReader as fdr

# 원본 엔진 모듈 경로 추가
sys.path.append(os.getcwd())
from engine.strategy import build_signals_and_targets, get_market_regime
# 순정 지표 엔진
from engine.indicators import calculate_adx
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def clean_df(df):
    if df is None or df.empty: return None
    df.columns = [str(c).capitalize() for c in df.columns]
    if 'Date' not in df.columns: df = df.reset_index().rename(columns={'index': 'Date'})
    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
    return df.sort_values('Date')

def prepare_indicators(df):
    df_in = df.copy()
    df_in.columns = [str(c).lower() for c in df_in.columns]
    df_in = calculate_adx(df_in)
    df_cap = df.copy()
    df_in['mfi'] = calculate_mfi(df_cap)
    df_in['intraday_intensity'] = calculate_intraday_intensity(df_cap).rolling(window=21).sum()
    return df_in

def debug_specific_trade():
    print("--- [DEEP DEBUG: TRADE VIOLATION 2023-03-02] ---")
    ticker_tk, ticker_name = "379800", "KODEX 미국S&P500TR"
    warmup_start = "2018-01-01"
    end_date = "2026-04-03"
    
    # 1. 데이터 로드
    k200 = clean_df(fdr.DataReader("069500", start=warmup_start, end=end_date))
    target = clean_df(fdr.DataReader(ticker_tk, start=warmup_start, end=end_date))
    
    # 2. 지표 연산
    k200_p = prepare_indicators(k200)
    target_p = prepare_indicators(target)
    
    # 3. 신호 생성 (MASTER SYNC 재현)
    k200_signals = build_signals_and_targets(k200_p, "KODEX 200", turbo_discount=0.5)
    regime_series = get_market_regime(k200_signals, use_global_mfi=True)
    regime_series.index = k200_signals['date'].values
    
    target_sync = target_p.set_index('date').reindex(k200_p.set_index('date').index).reset_index().ffill().fillna(0)
    reg_aligned = regime_series.reindex(target_sync.set_index('date').index).fillna(True)
    
    signals = build_signals_and_targets(target_sync, ticker_name=ticker_name, is_bull_market=reg_aligned, turbo_discount=0.5)
    
    # 4. 2023-03-02 진입 건 대조 (진입일이 T+1이므로 T는 2023-02-28 또는 직전 영업일)
    # 2023-03-02는 목요일. 전일은 2023-02-28(화) (3월 1일은 공휴일)
    print("\n[SIGNAL DUMP: 2023-02-28 ~ 2023-03-02]")
    subset = signals[(signals['date'] >= "2023-02-24") & (signals['date'] <= "2023-03-03")]
    print(subset[['date', 'execute_buy_T_plus_1', 'close', 'target_break_price', 'mfi', 'intraday_intensity', 'adx_14']])

if __name__ == "__main__":
    debug_specific_trade()
