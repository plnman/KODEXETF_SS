import pandas as pd
import yfinance as yf
import sys
import os

# 현재 경로 추가 (전략 및 백테스터 로딩용)
sys.path.append(os.getcwd())
from engine.strategy import build_signals_and_targets
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

def generate_report():
    # 1. 데이터 로드 (2019년부터 전수 데이터)
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2019-01-01", progress=False)
    
    # 벤치마크 데이터 (^KS200) - yfinance에서 직접 로드
    bm_data = yf.download("^KS200", start="2019-01-01", progress=False)['Close']
    bm_data = bm_data.ffill()

    # 모든 종목 시그널 생성 (최신 V3.1.3 파라미터 적용)
    all_signals = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = data.xs(raw_ticker, level=1, axis=1).ffill().dropna().reset_index()
        df_clean.rename(columns={'Date': 'date'}, inplace=True)
        df_clean.columns = [c.lower() for c in df_clean.columns]
        
        # 수급 지표 계산
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        
        # 최적화된 파라미터(K=0.4, MFI=55, ADX=15)로 시그널 생성
        all_signals[name] = build_signals_and_targets(df_clean, ticker_name=name)

    # 포트폴리오 백테스트 실행 (3종목 집중 투자)
    res = run_portfolio_backtest(all_signals, max_tickers=3, weight_per_ticker=0.33)
    hist = res['history'].set_index('date')
    hist.index = pd.to_datetime(hist.index)
    
    # 연도별 수익률 산출
    y_last = hist.resample('YE').last()
    y_irp = pd.Series([50000000] + y_last['total_value'].tolist()).pct_change().dropna() * 100
    
    bm_reindexed = bm_data.reindex(hist.index).ffill()
    bm_last = bm_reindexed.resample('YE').last()
    # [FIX] DataFrame인 경우 첫 번째 컬럼을 추출하여 Series로 변환
    if isinstance(bm_last, pd.DataFrame):
        bm_last_vals = bm_last.iloc[:, 0].tolist()
        bm_first_val = bm_reindexed.iloc[0, 0] if isinstance(bm_reindexed, pd.DataFrame) else bm_reindexed.iloc[0]
        bm_final_val = bm_reindexed.iloc[-1, 0] if isinstance(bm_reindexed, pd.DataFrame) else bm_reindexed.iloc[-1]
    else:
        bm_last_vals = bm_last.tolist()
        bm_first_val = bm_reindexed.iloc[0]
        bm_final_val = bm_reindexed.iloc[-1]

    y_ko = pd.Series([bm_first_val] + bm_last_vals).pct_change().dropna() * 100
    
    years = y_last.index.year
    
    # 총계 산출
    total_irp = (res['final_capital']/50000000 - 1) * 100
    total_ko = (bm_final_val / bm_first_val - 1) * 100
    
    print(f"TOTAL|{total_irp:.2f}|{total_ko:.2f}|{total_irp-total_ko:+.2f}")
    for y, ir, ko in zip(years, y_irp, y_ko):
        print(f"{y}|{ir:.2f}|{ko:.2f}|{ir-ko:+.2f}")

if __name__ == "__main__":
    generate_report()
