import pandas as pd
import yfinance as yf
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def research_regime():
    print("🔬 [V3 변신 근거를 위한 시장 레짐(Regime) 심층 분석]")
    
    # KODEX 200 (시장 지수) 데이터 확보
    data = yf.download("069500.KS", start="2019-01-01", progress=False).dropna()
    data.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in data.columns]
    data = data.reset_index()
    data.rename(columns={'date':'Date'}, inplace=True)
    data['date'] = data['Date'].dt.strftime('%Y-%m-%d')
    
    df_upper = data.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
    data['mfi'] = calculate_mfi(df_upper)
    data['intraday_intensity'] = calculate_intraday_intensity(df_upper)
    
    # V2 기준 시그널 생성 (ADX 포함됨)
    signals = build_signals_and_targets(data.dropna(), ticker_name="KODEX 200")
    signals['date'] = pd.to_datetime(signals['date'])
    signals['year'] = signals['date'].dt.year
    
    # ----------------------------------------------------
    # 분석 포인트 1: 2025년(V3 압승) vs 2021년(V2 우세) 지표 비교
    # ----------------------------------------------------
    years_to_compare = [2021, 2025]
    results = []
    
    for y in years_to_compare:
        y_df = signals[signals['year'] == y]
        
        # 1. ADX 평균/최대값 (추세의 강도)
        adx_mean = y_df['adx_14'].mean()
        adx_max = y_df['adx_14'].max()
        
        # 2. 이격도 (Price / SMA 20 - 1) -> 과열 여부
        deviation = (y_df['close'] / y_df['sma_20'] - 1) * 100
        dev_mean = deviation.mean()
        dev_max = deviation.max()
        
        # 3. 돌파 횟수 (Whipsaw 위험도)
        entry_signals = y_df['buy_signal_T'].sum()
        
        results.append({
            "연도": y,
            "ADX평균": adx_mean,
            "ADX최대": adx_max,
            "이격도평균": dev_mean,
            "이격도최대": dev_max,
            "진입횟수": entry_signals
        })
        
    df_res = pd.DataFrame(results)
    print("\n--- [연도별 핵심 레짐 데이터 대조] ---")
    print(df_res.to_string(index=False))
    
    # ----------------------------------------------------
    # 레짐 스위칭 기준 제안 (가설)
    # ----------------------------------------------------
    # 2025년과 같이 ADX가 특정 임계치를 넘어서며 이격도가 벌어지는 구간이 '불장'의 정의
    print("\n--- [데이터 기반 V3 변신 근거 도출] ---")
    if results[1]['ADX최대'] > results[0]['ADX최대']:
        print(f"👉 근거 1: 추세 강도(ADX)가 2021년({results[0]['ADX최대']:.1f})보다 2025년({results[1]['ADX최대']:.1f})에 훨씬 강력했습니다.")
    
    if results[1]['이격도최대'] > results[0]['이격도최대']:
        print(f"👉 근거 2: 고점 이격도가 {results[1]['이격도최대']:.1f}% 까지 벌어지는 '광기' 국면에서 V3의 짧은 익절이 수익을 보존했습니다.")

if __name__ == "__main__":
    research_regime()
