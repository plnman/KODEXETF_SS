"""
scripts/run_backtest_v380.py
============================
V3.8.0 15종목 신규 유니버스 백테스트 스탠드얼론 실행기.

실행:
  python scripts/run_backtest_v380.py

출력:
  - 3/5/10종목 누적수익률, CAGR, MDD
  - STABLE_ROI / BASELINE_RET_MAP 업데이트 제안값
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime

from config.etf_universe import TARGET_ETFS, ETFS_CLEAN
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.portfolio_backtester import run_portfolio_backtest

START_DATE = "2019-01-01"
END_DATE   = "2026-04-04"

def clean_df(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    if 'date' not in df.columns:
        df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    return df.sort_values('date')


def load_ticker(code, name):
    clean = code.replace(".KS", "")
    try:
        df = fdr.DataReader(clean, start=START_DATE, end=END_DATE)
        if df is None or df.empty:
            print(f"  [SKIP] {name} ({clean}) — 데이터 없음")
            return None
        df = clean_df(df)
        df = df[(df['date'] >= "2019-01-02") & (df['date'] <= "2026-04-03")]
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        print(f"  [OK]   {name} ({clean}) — {len(df)} rows")
        return df
    except Exception as e:
        print(f"  [ERR]  {name} ({clean}) — {e}")
        return None


def main():
    print("=" * 60)
    print(f" V3.8.0 백테스트 ({START_DATE} ~ {END_DATE})")
    print(f" 유니버스: {len(TARGET_ETFS)}종목")
    print("=" * 60)

    # K200 마스터 캘린더
    print("\n[1/3] K200 마스터 캘린더 로드...")
    k200_raw = fdr.DataReader("069500", start=START_DATE, end=END_DATE)
    k200_raw = clean_df(k200_raw)
    k200_raw = k200_raw[(k200_raw['date'] >= "2019-01-02") & (k200_raw['date'] <= "2026-04-03")]
    k200_raw['mfi'] = calculate_mfi(k200_raw)
    k200_raw['intraday_intensity'] = calculate_intraday_intensity(k200_raw)
    print(f"  K200: {len(k200_raw)} rows")

    # 레짐 판독
    k200_signals = build_signals_and_targets(k200_raw, "KODEX 200", turbo_discount=0.5)
    regime_series = get_market_regime(k200_signals, use_global_mfi=True)

    # 전체 종목 로드
    print(f"\n[2/3] 15종목 로드 중...")
    all_signals = {}
    for raw_code, name in TARGET_ETFS.items():
        df = load_ticker(raw_code, name)
        if df is None:
            continue
        df_sync = df.set_index('date').reindex(k200_raw.set_index('date').index).reset_index().ffill().fillna(0)
        df_sync = df_sync.drop_duplicates(subset=['date'])
        regime_aligned = regime_series.reindex(df_sync.set_index('date').index).fillna(True)
        sig = build_signals_and_targets(df_sync, ticker_name=name, is_bull_market=regime_aligned, turbo_discount=0.4)
        all_signals[name] = sig

    loaded = len(all_signals)
    print(f"\n  로드 완료: {loaded}/{len(TARGET_ETFS)} 종목")

    # 백테스트 실행
    print(f"\n[3/3] 백테스트 실행 중 (3/5/10 종목)...")
    results = {}
    for n in [3, 5, 10]:
        print(f"  max_tickers={n} ...", end=" ", flush=True)
        res = run_portfolio_backtest(all_signals, 50_000_000.0, n, True)
        results[n] = res
        print(f"누적수익률={res['cumulative_return']:.2f}%  CAGR={res['cagr']:.2f}%  MDD={res['mdd']:.2f}%")

    # 결과 출력
    print("\n" + "=" * 60)
    print(" 최종 결과 요약")
    print("=" * 60)
    print(f"{'종목수':>6}  {'누적수익률':>10}  {'CAGR':>8}  {'MDD':>8}  {'최종자산':>14}")
    print("-" * 60)
    for n, res in results.items():
        print(f"{n:>6}  {res['cumulative_return']:>10.2f}%  {res['cagr']:>7.2f}%  {res['mdd']:>7.2f}%  {res['final_capital']:>14,.0f}원")

    print("\n" + "=" * 60)
    print(" 코드 업데이트 제안 (config/etf_universe.py 및 frontend/app.py)")
    print("=" * 60)
    r5 = results[5]['cumulative_return']
    r3 = results[3]['cumulative_return']
    r10 = results[10]['cumulative_return']
    print(f"\n# frontend/app.py")
    print(f"STABLE_ROI = {r5:.2f}  # V3.8.0 5종목 기준")
    print(f"\n# frontend/app.py (main 함수 내)")
    print(f"BASELINE_RET_MAP = {{3: {r3:.2f}, 5: {r5:.2f}, 10: {r10:.2f}}}")
    print()


if __name__ == "__main__":
    main()
