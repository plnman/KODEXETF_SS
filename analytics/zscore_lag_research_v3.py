import pandas as pd
import yfinance as yf
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def simulate_realtime_lag_v3():
    print("🔬 [실시간 레짐 판독 지연(Lag) 및 부작용 정밀 시뮬레이션 V3]")
    
    data = yf.download("069500.KS", start="2023-01-01", end="2026-03-31", progress=False).dropna()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [c[0].lower() for c in data.columns]
    else:
        data.columns = [c.lower() for c in data.columns]
    
    data = data.reset_index()
    if 'Date' in data.columns:
        data.rename(columns={'Date': 'date'}, inplace=True)
    elif 'index' in data.columns:
        data.rename(columns={'index': 'date'}, inplace=True)
        
    data['date_dt'] = pd.to_datetime(data['date'])
    data['date'] = data['date_dt'].dt.strftime('%Y-%m-%d')
    
    df_upper = data.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
    data['mfi'] = calculate_mfi(df_upper)
    data['intraday_intensity'] = calculate_intraday_intensity(df_upper)
    
    signals = build_signals_and_targets(data.dropna(), ticker_name="KODEX 200")
    
    window = 252
    signals['adx_mean'] = signals['adx_14'].rolling(window=window).mean()
    signals['adx_std'] = signals['adx_14'].rolling(window=window).std()
    signals['adx_zscore'] = (signals['adx_14'] - signals['adx_mean']) / signals['adx_std']
    
    signals['bull_mode'] = signals['adx_zscore'] > 2.0
    
    print(f"\n--- [2025년 불장 전체 트리거 시점 추적] ---")
    analysis_range = signals[(signals['date'] >= '2025-01-01') & (signals['date'] <= '2025-12-31')]
    
    trigger_date = None
    for _, row in analysis_range.iterrows():
        if trigger_date is None and row['bull_mode']:
            trigger_date = row['date']
            print(f"!!! [TRIGGER] {trigger_date} 에 V3 공격 모드 변환 !!!")
            print(f" -> 지점가: {row['close']:,.0f} | Z-Score: {row['adx_zscore']:.2f} | ADX: {row['adx_14']:.2f}")

    if trigger_date is None:
        print("??? 2025년에 Z-Score > 2.0 인 날이 없었습니다. 임계치 조정이 필요할 수 있습니다.")
        print(f"2025년 Z-Score 최대값: {analysis_range['adx_zscore'].max():.2f}")

if __name__ == "__main__":
    simulate_realtime_lag_v3()
