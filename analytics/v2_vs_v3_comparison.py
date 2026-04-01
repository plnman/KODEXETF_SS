import pandas as pd
import yfinance as yf
import sys
import os
import warnings

warnings.filterwarnings('ignore')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine.strategy as strategy_v2
import engine.strategy_v3 as strategy_v3
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

def run_comparison():
    print("🚀 [V2(현행) vs V3(공세적 보강) 성과 비교 시뮬레이션 가동]")
    
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2018-12-20", end="2026-03-31", progress=False)
    
    # 공통 데이터 전처리
    clean_dfs = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df = data.xs(raw_ticker, axis=1, level=1).dropna().reset_index()
        df.columns = [c.lower() for c in df.columns]
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        df_upper = df.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df['mfi'] = calculate_mfi(df_upper)
        df['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        clean_dfs[name] = df.dropna().reset_index(drop=True)

    # 1. V2 (현행) 시그널 생성
    signals_v2 = {}
    for name, df in clean_dfs.items():
        signals_v2[name] = strategy_v2.build_signals_and_targets(df.copy(), ticker_name=name)
    
    # 2. V3 (보강) 시그널 생성
    signals_v3 = {}
    for name, df in clean_dfs.items():
        signals_v3[name] = strategy_v3.build_signals_and_targets(df.copy(), ticker_name=name)

    # 3. 백테스트 가동
    res_v2 = run_portfolio_backtest(signals_v2, initial_capital=50000000.0)
    res_v3 = run_portfolio_backtest(signals_v3, initial_capital=50000000.0)

    # 4. 연도별 통계 추출 함수
    def get_metrics(res_dict):
        hist = res_dict['history'].copy()
        hist['date'] = pd.to_datetime(hist['date'])
        hist['year'] = hist['date'].dt.year
        
        # MDD 계산
        cum_max = hist['total_value'].cummax()
        drawdown = (hist['total_value'] - cum_max) / cum_max
        mdd = drawdown.min() * 100
        
        annual = {}
        years = sorted(hist['year'].unique())
        prev_val = 50000000.0
        for y in years:
            year_end_val = hist[hist['year'] == y]['total_value'].iloc[-1]
            annual[y] = (year_end_val / prev_val - 1) * 100
            prev_val = year_end_val
        return annual, mdd

    v2_annual, v2_mdd = get_metrics(res_v2)
    v3_annual, v3_mdd = get_metrics(res_v3)

    # 5. 결과 출력
    print("\n" + "="*60)
    print(f"{'연도':^6} | {'V2(현행) 수익률':^15} | {'V3(보강) 수익률':^15} | {'차이(Alpha)':^10}")
    print("-" * 60)
    
    all_years = sorted(list(set(v2_annual.keys()) | set(v3_annual.keys())))
    for y in all_years:
        v2_ret = v2_annual.get(y, 0)
        v3_ret = v3_annual.get(y, 0)
        diff = v3_ret - v2_ret
        print(f"{y:^8} | {v2_ret:^18.2f}% | {v3_ret:^18.2f}% | {diff:+^12.2f}%")
        
    print("-" * 60)
    v2_total = (res_v2['final_capital'] / 50000000.0 - 1) * 100
    v3_total = (res_v3['final_capital'] / 50000000.0 - 1) * 100
    print(f"{'누적 합계':^6} | {v2_total:^18.2f}% | {v3_total:^18.2f}% | {v3_total - v2_total:+^12.2f}%")
    print(f"{'최대낙폭(MDD)':^4} | {v2_mdd:^18.2f}% | {v3_mdd:^18.2f}% | {v3_mdd - v2_mdd:+^12.2f}%")
    print("="*60)
    
    print(f"\n[최종 진단]")
    if v3_total > v2_total:
        print(f"👉 V3 엔진이 전체적으로 {v3_total - v2_total:.2f}%p 더 높은 성과를 보였습니다.")
        if v3_annual.get(2025, 0) > v2_annual.get(2025, 0):
            print(f"✅ 특히 아쉬워하셨던 2025년 불장에서 {v3_annual[2025] - v2_annual[2025]:.2f}%p 수익률 개선이 확인되었습니다.")
    else:
        print(f"👉 V3 엔진이 기대보다 성과가 낮았습니다. 파라미터 재조정이 필요할 수 있습니다.")

if __name__ == "__main__":
    run_comparison()
