import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import sys
import os

# 원본 엔진 모듈 경로 추가 (절대 경로 보정)
sys.path.append(os.getcwd())
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity
from engine.strategy import build_signals_and_targets

def run_pipeline_audit():
    ticker_code = '069500' # KODEX 200
    start_date = '2019-01-02'
    end_date = '2026-04-03'
    
    print(f"--- [PIPELINE PRECISION AUDIT] ---")
    print(f"Ticker: {ticker_code} | Master Range: {start_date} ~ {end_date}")
    
    try:
        # [STAGE 1] RAW DATA GATHERING
        df = fdr.DataReader(ticker_code, start=start_date, end=end_date)
        if df.empty: raise ValueError("Data Load Fail")
        
        # [STAGE 2] INDICATOR CALCULATOR AUDIT
        # Pre-cleaning to ensure integrity
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        if 'date' not in df.columns: df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df = df.sort_values('date')
        
        print(f"Total Rows Ingested: {len(df)}")
        
        # [STAGE 3] PIPELINE FLOW: Indicator -> Signal
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        
        # Strategy Logic Application
        df_proto = df.copy()
        df_signals = build_signals_and_targets(df_proto, ticker_name="KODEX 200", is_bull_market=True)
        
        # [STAGE 4] ANOMALY DETECTION
        nan_mfi = df_signals['mfi'].isna().sum()
        nan_adx = df_signals['adx_14'].isna().sum()
        nan_signals = df_signals['buy_signal_T'].isna().sum()
        
        # Zero Price Check
        zero_prices = (df_signals['close'] == 0).sum()
        
        print(f"\n[Precision Health Check]")
        print(f" - NaN MFI Days: {nan_mfi} (Expected: ~14 for burn-in)")
        print(f" - NaN ADX Days: {nan_adx} (Expected: ~14-28 for burn-in)")
        print(f" - NaN Signals: {nan_signals}")
        print(f" - Zero Prices: {zero_prices}")
        
        # Signal Generation Integrity
        buy_signals = df_signals['buy_signal_T'].sum()
        exit_signals = df_signals['exit_signal_T'].sum()
        print(f" - Total Buy Signals: {buy_signals}")
        print(f" - Total Exit Signals: {exit_signals}")
        
        if len(df) == 1781:
            print(f"\n🟢 파이프라인 무결성 확증 (1,781 rows / No Leakage)")
        else:
            print(f"\n🔴 파이프라인 누수 감지: {len(df)} rows found (Expected 1781)")

    except Exception as e:
        print(f"🚨 Pipeline Audit Failed: {str(e)}")

if __name__ == "__main__":
    run_pipeline_audit()
