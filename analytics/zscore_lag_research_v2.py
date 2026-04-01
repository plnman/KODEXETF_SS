import pandas as pd
import yfinance as yf
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def simulate_realtime_lag_v2():
    print("🔬 [실시간 레짐 판독 지연(Lag) 및 부작용 정밀 시뮬레이션 V2]")
    
    # 2023년부터 가져와서 252개 버퍼 확보
    data = yf.download("069500.KS", start="2023-01-01", end="2026-03-31", progress=False).dropna()
    # 컬럼 처리
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
    
    # Z-Score 연산 (실시간 창 252일)
    window = 252
    signals['adx_mean'] = signals['adx_14'].rolling(window=window).mean()
    signals['adx_std'] = signals['adx_14'].rolling(window=window).std()
    signals['adx_zscore'] = (signals['adx_14'] - signals['adx_mean']) / signals['adx_std']
    
    # 분석용 플래그
    signals['bull_mode'] = signals['adx_zscore'] > 2.0
    
    print(f"\n--- [2025년 불장 초기 판독 데이터 (지연 시간 체크)] ---")
    # 2025년 3월부터 5월까지가 본격 상승기임
    analysis_range = signals[(signals['date'] >= '2025-01-01') & (signals['date'] <= '2025-06-01')]
    
    trigger_date = None
    for _, row in analysis_range.iterrows():
        status = "🔥 불장모드(V3)" if row['bull_mode'] else "🛡️ 안정모드(V2)"
        if trigger_date is None and row['bull_mode']:
            trigger_date = row['date']
            print(f"!!! [TRIGGER] {trigger_date} 에 V3 공격 모드로 변신 완료 !!!")
            
        if row['date'] in ['2025-01-02', '2025-03-03', '2025-04-01', '2025-05-02']:
            print(f"날짜: {row['date']} | 종가: {row['close']:,.0f} | ADX: {row['adx_14']:.2f} | Z-Score: {row['adx_zscore']:.2f} | 상태: {status}")

    # 지연율 계산 (상승 시작 대비 트리거 시점)
    # 2025년 저점은 대략 1월 초
    if trigger_date:
        low_price = signals[signals['date'] == '2025-01-02']['close'].iloc[0]
        trigger_price = signals[signals['date'] == trigger_date]['close'].iloc[0]
        lag_pct = (trigger_price / low_price - 1) * 100
        print(f"\n[트리거 정밀 진단]")
        print(f" - 상승 시작 저점 대비 지연: {lag_pct:.1f}% 지점에서 모드 변환 완료")

if __name__ == "__main__":
    simulate_realtime_lag_v2()
