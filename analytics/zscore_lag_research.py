import pandas as pd
import yfinance as yf
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def simulate_realtime_lag():
    print("🔬 [실시간 레짐 판독 지연(Lag) 및 부작용 정밀 시뮬레이션]")
    
    # 2025년 불장 초기 진입 구간 집중 분석 (2024년 말 ~ 2025년 초)
    data = yf.download("069500.KS", start="2024-01-01", end="2026-03-31", progress=False).dropna()
    data.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in data.columns]
    data = data.reset_index()
    data.rename(columns={'Date': 'date', 'index': 'date'}, inplace=True)
    data['date_dt'] = pd.to_datetime(data['date'])
    data['date'] = data['date_dt'].dt.strftime('%Y-%m-%d')
    
    df_upper = data.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
    data['mfi'] = calculate_mfi(df_upper)
    data['intraday_intensity'] = calculate_intraday_intensity(df_upper)
    
    signals = build_signals_and_targets(data.dropna(), ticker_name="KODEX 200")
    
    # Z-Score 연산 (실시간 창 252일)
    window = 252
    signals['adx_mean'] = signals['adx_14'].rolling(window=window).mean()
    signals['adx_std'] = signals['adx_14'].rolling(window=window).std()
    signals['adx_zscore'] = (signals['adx_14'] - signals['adx_mean']) / signals['adx_std']
    
    # 분석용 플래그
    signals['bull_mode'] = signals['adx_zscore'] > 2.0
    
    # 2025년 초 불장 발생 시점 대조
    bull_start_date = "2025-01-02" # 2025년 첫 거래일
    print(f"\n--- [2025년 불장 초기 판독 데이터] ---")
    
    analysis_range = signals[(signals['date'] >= '2024-12-15') & (signals['date'] <= '2025-02-15')]
    
    for _, row in analysis_range.iterrows():
        status = "🔥 불장모드(V3)" if row['bull_mode'] else "🛡️ 안정모드(V2)"
        print(f"날짜: {row['date']} | 종가: {row['close']:,.0f} | ADX: {row['adx_14']:.2f} | Z-Score: {row['adx_zscore']:.2f} | 상태: {status}")

    # 잦은 스위칭(Flip-flop) 여부 확인
    signals['mode_change'] = signals['bull_mode'].diff().fillna(0).abs()
    total_changes = signals['mode_change'].sum()
    print(f"\n[부작용 진단 데이터]")
    print(f"1. 전체 시뮬레이션 기간 중 모드 전환 횟수: {int(total_changes)}회")
    print(f"2. 평균 모드 유지 기간: {len(signals)/total_changes if total_changes > 0 else len(signals):.1f}일")

if __name__ == "__main__":
    simulate_realtime_lag()
