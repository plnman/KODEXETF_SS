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
    print("[검증] V3.4.0 vs KODEX 200 (Buy & Hold) 연도별 수익률 비교")
    
    start_date = "2019-01-01"
    all_data = {}
    for tk, name in TARGET_ETFS.items():
        df = yf.download(tk, start=start_date, progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        df = df.dropna()
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns] 
        df['date'] = pd.to_datetime(df['date'])
        
        # 날짜순 정렬 (필수)
        df = df.sort_values('date')
        all_data[name] = df.copy()

    # KODEX 200 B&H (Benchmark)
    k200_df = all_data["KODEX 200"]
    k200_df['year'] = k200_df['date'].dt.year
    
    # KODEX 200 연도별 수익률 (B&H: 해당 연도 첫날 시가 대비 마지막 날 종가)
    def calc_yearly_return(x):
        return (x['close'].iloc[-1] / x['open'].iloc[0] - 1) * 100
    kospi_yearly = k200_df.groupby('year').apply(calc_yearly_return)

    # V3.4.0 엔진 가동
    k200_sigs = build_signals_and_targets(k200_df, "KODEX 200", turbo_discount=0.5)
    regime = get_market_regime(k200_sigs, use_global_mfi=True)
    
    all_signals = {}
    for name, df in all_data.items():
        df_sync = df.set_index('date').reindex(k200_df.set_index('date').index).reset_index().ffill().fillna(0)
        df_sync = df_sync.drop_duplicates(subset=['date'])
        
        sig = build_signals_and_targets(df_sync, name, is_bull_market=regime, turbo_discount=0.5)
        # 백테스터 포맷에 맞게 문자열로 변환
        sig['date'] = pd.to_datetime(sig['date']).dt.strftime('%Y-%m-%d')
        all_signals[name] = sig

    res = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=3, use_cash_sweep=True)
    history = res['history']
    
    hist_df = pd.DataFrame(history)
    hist_df['date'] = pd.to_datetime(hist_df['date'])
    hist_df['year'] = hist_df['date'].dt.year
    
    # 알고리즘 연도별 수익률 (기본적으로 복리 누적되므로, 각 연도별 첫 자산 대비 마지막 자산의 증감률)
    def calc_alg_yearly_return(x):
        return (x['total_value'].iloc[-1] / x['total_value'].iloc[0] - 1) * 100
    alg_yearly = hist_df.groupby('year').apply(calc_alg_yearly_return)

    # DataFrame 병합
    comparison_df = pd.DataFrame({
        'KODEX 200 (B&H) %': kospi_yearly,
        'V3.4.0 Algorithm %': alg_yearly
    })
    comparison_df['Alpha (Outperformance) %p'] = comparison_df['V3.4.0 Algorithm %'] - comparison_df['KODEX 200 (B&H) %']
    
    print("\n" + "="*65)
    print(" [결과] 연도별 수익률: V3.4.0 vs KOSPI 200 (B&H) ")
    print("="*65)
    print(comparison_df.round(2).to_string())
    print("="*65)
    
    k200_cum = (k200_df['close'].iloc[-1] / k200_df['open'].iloc[0] - 1) * 100
    alg_cum = res['cumulative_return']
    print(f"\n[누적 요약]")
    print(f"- KOSPI 200 (B&H): {k200_cum:.2f}%")
    print(f"- V3.4.0 Algorithm: {alg_cum:.2f}%")
    print(f"-> 최종 알고리즘이 KOSPI 200 대비 {alg_cum - k200_cum:.2f}%p 아웃퍼폼!")

if __name__ == "__main__":
    main()
