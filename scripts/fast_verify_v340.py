
import pandas as pd
import yfinance as yf
from datetime import datetime
import sys
import os

sys.path.append(os.getcwd())
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import TARGET_ETFS, calculate_mfi, calculate_intraday_intensity

def main():
    print("[코드 레벨 검증] 현재 실전 코드(V3.4.0) 백테스트 가동 중...")
    
    # 1. 데이터 로드 (Standard Close)
    start_date = "2019-01-01"
    all_data = {}
    for tk, name in TARGET_ETFS.items():
        df = yf.download(tk, start=start_date, progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=lambda x: x.capitalize())
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        df = df.dropna()
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns] # reset index 이후에 컬럼명을 lower 하도록 변경
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        all_data[name] = df

    # 2. 레짐 판독 및 시그널 생성
    k200_df = all_data["KODEX 200"]
    k200_sigs = build_signals_and_targets(k200_df, "KODEX 200")
    regime = get_market_regime(k200_sigs)
    
    all_signals = {}
    for name, df in all_data.items():
        df_sync = df.set_index('date').reindex(k200_df.set_index('date').index).reset_index().ffill().fillna(0)
        df_sync = df_sync.drop_duplicates(subset=['date'])
        
        # 전략 실행 (내부에 np.where 등 모든 신규 로직 반영됨)
        sig = build_signals_and_targets(df_sync, name, is_bull_market=regime)
        
        # 전략을 돌렸으면, 내부에서 계산된 execute_buy/exit 플래그를 그대로 사용해야 함
        all_signals[name] = sig

    # 3. 박멸 엔진 호출
    res = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=3)
    
    print(f"\n[결과] 실전 코드 최종 누적 수익률: {res['cumulative_return']:.2f}%")
    print(f"[결과] MDD (최대 낙폭): {res['mdd']:.2f}%")

if __name__ == "__main__":
    main()
