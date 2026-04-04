import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import sys
import os

# 프로젝트 경로 설정
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

# V3.4.0 단일 엔진 (무결성 최상위 원칙)
from engine.strategy import build_signals_and_targets, get_market_regime
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def run_dual_engine_audit():
    print(f"🚦 [이중 데이터 검증] 단일 엔진(Single Engine) 무결성 구동 테스트")
    start_date = "2023-01-01"
    
    # KODEX 200 (YF 069500.KS vs Naver 069500)
    ticker_name = "KODEX 200"
    yf_ticker = "069500.KS"
    naver_ticker = "069500"
    
    print("-" * 60)
    print("1. [YF] 야후 파이낸스 데이터 로딩 및 전처리...")
    df_yf_raw = yf.download(yf_ticker, start=start_date, progress=False)
    if isinstance(df_yf_raw.columns, pd.MultiIndex):
        df_yf_raw.columns = df_yf_raw.columns.get_level_values(0)
    df_yf_raw = df_yf_raw.dropna().reset_index()
    df_yf_raw.rename(columns={'Date': 'Date'}, inplace=True) # Ensure 'Date' exists
    
    print("2. [Naver] 네이버 증권 데이터 로딩 및 전처리...")
    df_naver_raw = fdr.DataReader(naver_ticker, start=start_date).reset_index()
    # FDR uses Title Case Date
    
    def prep_and_calculate(df_raw, source_name):
        df = df_raw.copy()
        # 공통 칼럼 매핑
        df.rename(columns={'Date': 'Date', 'date': 'Date'}, inplace=True)
        df.columns = [c.capitalize() for c in df.columns]
        
        # 무결성 원칙 적용: [동일한 보조지표 연산 로직]
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        
        df = df.dropna().reset_index(drop=True)
        df.columns = [c.lower() for c in df.columns]
        return df

    df_yf = prep_and_calculate(df_yf_raw, "YF")
    df_naver = prep_and_calculate(df_naver_raw, "Naver")
    
    print("3. [YF vs Naver] 동일한 V3.4.0 엔진(build_signals_and_targets) 투입...")
    # 무결성 핵심 규칙 반영: 동일 파라미터, 동일 함수 호출
    signals_yf = build_signals_and_targets(df_yf, ticker_name)
    signals_naver = build_signals_and_targets(df_naver, ticker_name)
    
    # 최신일 기준 비교
    last_yf = signals_yf.iloc[-1]
    last_naver = signals_naver.iloc[-1]
    
    print("\n🚦 [최종 결과 대조표] (기준일: 최신장 마감)")
    print(f"                     | [YF 엔진]         | [Naver 엔진]     | 일치(오차)")
    print(f"-----------------------------------------------------------------------")
    
    # 핀셋 대조
    p_diff = abs(last_yf['close'] - last_naver['close'])
    t_diff = abs(last_yf['target_break_price'] - last_naver['target_break_price'])
    m_diff = abs(last_yf['mfi'] - last_naver['mfi'])
    r_diff = abs(last_yf['composite_rs'] - last_naver['composite_rs'])
    
    print(f"종가(Close)          | {last_yf['close']:,.0f}          | {last_naver['close']:,.0f}          | {'🟢' if p_diff < 5 else '🔴'}")
    print(f"목표가(Target Price) | {last_yf['target_break_price']:.2f}     | {last_naver['target_break_price']:.2f}     | {'🟢' if t_diff < 5 else '🔴'}")
    print(f"자금유입강도(MFI)   | {last_yf['mfi']:.2f}           | {last_naver['mfi']:.2f}           | {'🟢' if m_diff < 1 else '🔴'}")
    print(f"종합RS점수(Score)    | {last_yf['composite_rs']:.4f}         | {last_naver['composite_rs']:.4f}         | {'🟢' if r_diff < 0.01 else '🔴'}")
    
    if (p_diff < 5) and (t_diff < 5) and (m_diff < 1):
        print("\n✅ V3.4.0 시스템 코어 엔진의 파이프라인 무결성이 입증되었습니다.")
    else:
        print("\n⚠️ 원천 데이터 간의 미세한 편차가 엔진 스노우볼을 통해 차이로 나타납니다.")

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
    run_dual_engine_audit()
