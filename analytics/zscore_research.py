import pandas as pd
import yfinance as yf
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def check_zscore_regime():
    print("🔬 [Z-Score 기반 무결성 레짐 필터 검증]")
    
    # KODEX 200 (시장 지수) 데이터 확보
    data = yf.download("069500.KS", start="2018-01-01", progress=False).dropna()
    # 멀티인덱스 처리
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [c[0].lower() for c in data.columns]
    else:
        data.columns = [c.lower() for c in data.columns]
    
    data = data.reset_index()
    # Reset index 후 첫 컬럼이 'Date'인지 확인
    if 'Date' in data.columns:
        data.rename(columns={'Date': 'date'}, inplace=True)
    elif 'index' in data.columns:
        data.rename(columns={'index': 'date'}, inplace=True)
        
    data['date_dt'] = pd.to_datetime(data['date'])
    data['date'] = data['date_dt'].dt.strftime('%Y-%m-%d')
    
    df_upper = data.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
    data['mfi'] = calculate_mfi(df_upper)
    data['intraday_intensity'] = calculate_intraday_intensity(df_upper)
    
    # 시그널 생성 (ADX 포함)
    signals = build_signals_and_targets(data.dropna(), ticker_name="KODEX 200")
    
    # ----------------------------------------------------
    # ADX Z-Score 계산 (과거 1년 기준 상대 강도)
    # ----------------------------------------------------
    window = 252
    signals['adx_mean'] = signals['adx_14'].rolling(window=window).mean()
    signals['adx_std'] = signals['adx_14'].rolling(window=window).std()
    signals['adx_zscore'] = (signals['adx_14'] - signals['adx_mean']) / signals['adx_std']
    
    signals['year'] = pd.to_datetime(signals['date']).dt.year
    
    z_res = []
    for y in [2021, 2022, 2023, 2024, 2025, 2026]:
        y_df = signals[signals['year'] == y]
        if y_df.empty: continue
        
        z_max = y_df['adx_zscore'].max()
        high_z_days = (y_df['adx_zscore'] > 1.5).sum()
        
        z_res.append({
            "연도": y,
            "Z-Score 최대": z_max,
            "불장 신호 일수": high_z_days
        })
        
    print("\n--- [ADX Z-Score 연도별 통계] ---")
    print(pd.DataFrame(z_res).to_string(index=False))

if __name__ == "__main__":
    check_zscore_regime()
