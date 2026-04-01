import pandas as pd
import yfinance as yf
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

def run_comparison():
    print("[V3.1 Hybrid Engine: Strategy Comparison Simulation]")
    print("Case A: 3-Ticker Focused (33.3% weight)")
    print("Case B: 10-Ticker Diversified (10% weight)\n")

    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2019-01-01", progress=False)
    
    # 1. 시장 레짐 판독 (KODEX 200 기준)
    k200_raw = pd.DataFrame()
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if (col, "069500.KS") in data.columns:
            k200_raw[col.lower()] = data[(col, "069500.KS")]
    k200_raw = k200_raw.dropna().reset_index()
    k200_raw['date'] = k200_raw['Date'].dt.strftime('%Y-%m-%d')
    df_upper_k2 = k200_raw.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
    k200_raw['mfi'] = calculate_mfi(df_upper_k2)
    k200_raw['intraday_intensity'] = calculate_intraday_intensity(df_upper_k2)
    k200_raw = k200_raw.dropna().reset_index(drop=True)
    k200_signals = build_signals_and_targets(k200_raw, ticker_name="KODEX 200")
    regime_series = get_market_regime(k200_signals)

    all_signals = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, raw_ticker) in data.columns:
                df_clean[col.lower()] = data[(col, raw_ticker)]
        if df_clean.empty: continue
        df_clean = df_clean.dropna().reset_index()
        df_clean['date'] = df_clean['Date'].dt.strftime('%Y-%m-%d')
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        df_clean = df_clean.dropna().reset_index(drop=True)
        # V3.1 하이브리드 시그널 생성 (레짐 벡터 주입)
        signals = build_signals_and_targets(df_clean, ticker_name=name, is_bull_market=regime_series)
        all_signals[name] = signals

    # [Case A] 3종목 집중
    res_a = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=3, weight_per_ticker=0.333)
    
    # [Case B] 10종목 분산
    res_b = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=10, weight_per_ticker=0.1)

    print("-" * 50)
    print(f"{'지표 (Metrics)':<20} | {'Case A (3종목)':<15} | {'Case B (10종목)':<15}")
    print("-" * 50)
    print(f"{'최종 누적 수익률':<20} | {((res_a['final_capital']/50000000)-1)*100:>14.2f}% | {((res_b['final_capital']/50000000)-1)*100:>14.2f}%")
    print(f"{'연평균 수익률(CAGR)':<20} | {res_a['cagr']:>14.2f}% | {res_b['cagr']:>14.2f}%")
    print(f"{'최대 낙폭(MDD)':<20} | {res_a['mdd']:>14.2f}% | {res_b['mdd']:>14.2f}%")
    print(f"{'최종 잔고':<20} | {res_a['final_capital']:>14,.0f}원 | {res_b['final_capital']:>14,.0f}원")
    print("-" * 50)

if __name__ == "__main__":
    run_comparison()
