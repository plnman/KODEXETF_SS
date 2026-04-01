import pandas as pd
import yfinance as yf
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

def investigate():
    print("🔍 [2025년 불장 성과 부진 심층 분석 시작]")
    
    tickers_list = list(TARGET_ETFS.keys())
    # 2025년과 그 전후 데이터를 충분히 가져옴
    data = yf.download(tickers_list, start="2024-01-01", end="2026-03-31", progress=False)
    
    all_signals = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df = data.xs(raw_ticker, axis=1, level=1).dropna().reset_index()
        df.columns = [c.lower() for c in df.columns]
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        
        df_upper = df.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df['mfi'] = calculate_mfi(df_upper)
        df['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        df = df.dropna().reset_index(drop=True)
        
        # V2 최적화 파라미터 적용
        all_signals[name] = build_signals_and_targets(df, ticker_name=name)
        
    res = run_portfolio_backtest(all_signals, initial_capital=50000000.0)
    trades = res['trades_df']
    trades['진입일자'] = pd.to_datetime(trades['진입일자'])
    trades['청산일자'] = pd.to_datetime(trades['청산일자'])
    
    trades_2025 = trades[trades['청산일자'].dt.year == 2025]
    
    print("\n--- 2025년 주요 매매 기록 ---")
    print(trades_2025[['종목명', '진입일자', '청산일자', '수익률(%)', '청산사유']].to_string())
    
    # 2025년 전체 시장(KODEX 200)의 움직임 대조
    k200 = all_signals['KODEX 200']
    k200['date'] = pd.to_datetime(k200['date'])
    k200_2025 = k200[k200['date'].dt.year == 2025]
    
    print("\n--- KODEX 200 (시장) 2025년 흐름 분석 ---")
    print(f"2025년 시작가: {k200_2025['open'].iloc[0]:,.0f}")
    print(f"2025년 최고가: {k200_2025['high'].max():,.0f}")
    print(f"2025년 종료가: {k200_2025['close'].iloc[-1]:,.0f}")
    
    # 전략적 약점 분석: 2025년 큰 상승장에서 '관망' 중이었던 기간 확인
    hist = res['history']
    hist['date'] = pd.to_datetime(hist['date'])
    hist_2025 = hist[hist['date'].dt.year == 2025]
    
    # 시장(K200) 수익률과 포트폴리오 수익률 상관관계 및 괴리 확인
    print("\n--- 포트폴리오 vs 시장 괴리 분석 ---")
    first_val = hist_2025['total_value'].iloc[0]
    last_val = hist_2025['total_value'].iloc[-1]
    print(f"포트폴리오 2025년 수익률: {(last_val/first_val - 1)*100:.2f}%")
    print(f"시장(K200) 2025년 수익률: {(k200_2025['close'].iloc[-1]/k200_2025['open'].iloc[0] - 1)*100:.2f}%")

if __name__ == "__main__":
    investigate()
