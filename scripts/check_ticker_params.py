"""
scripts/check_ticker_params.py
==============================
V3.8.0 종목별 파라미터 최적화 테이블 점검.

1. config/etf_universe.py 에서 TICKER_PARAMS 로드 확인
2. 각 종목 실제 데이터로 단일 백테스트 실행
3. 기본값(k=0.5, mfi=60, adx=20) 대비 수익률 개선 여부 확인

실행: python scripts/check_ticker_params.py
"""
import sys, os, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import FinanceDataReader as fdr
import pandas as pd

from config.etf_universe import ETF_UNIVERSE, TICKER_PARAMS
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.backtester import run_vectorized_backtest

START_DATE = "2019-01-01"
END_DATE   = "2026-04-04"
INITIAL_CAPITAL = 50_000_000.0

DEFAULT_PARAMS = {"k": 0.5, "mfi": 60, "adx_threshold": 20}


def load_and_prepare(raw_code: str, name: str, k200_raw, regime_series):
    clean = raw_code.replace(".KS", "")
    try:
        df = fdr.DataReader(clean, start=START_DATE, end=END_DATE)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        if 'date' not in df.columns:
            df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df = df.sort_values('date')
        df = df[(df['date'] >= "2019-01-02") & (df['date'] <= "2026-04-03")]
        if len(df) < 60:
            return None  # 데이터 부족 종목은 스킵
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)

        df_sync = df.set_index('date').reindex(
            k200_raw.set_index('date').index
        ).reset_index().ffill().fillna(0)
        df_sync = df_sync.drop_duplicates(subset=['date'])
        regime_aligned = regime_series.reindex(
            df_sync.set_index('date').index
        ).fillna(True)
        return df_sync, regime_aligned, len(df)
    except Exception as e:
        return None


def backtest_single(df_sync, regime_aligned, name, overrides=None):
    sig = build_signals_and_targets(
        df_sync, ticker_name=name,
        is_bull_market=regime_aligned, turbo_discount=0.4,
        overrides=overrides
    )
    res = run_vectorized_backtest(sig, INITIAL_CAPITAL)
    if "error" in res:
        return None
    cum_ret = (res['final_capital'] / INITIAL_CAPITAL - 1) * 100
    return {
        'cumret': round(cum_ret, 2),
        'trades': res['total_trades'],
        'winrate': res['win_rate'],
        'cagr': res['cagr'],
    }


def main():
    print("=" * 80)
    print(" V3.8.0 종목별 파라미터 최적화 테이블 점검")
    print("=" * 80)

    # ── Step 1: TICKER_PARAMS 출력 ────────────────────────────────────────────
    print(f"\n[1/3] config/etf_universe.py TICKER_PARAMS ({len(TICKER_PARAMS)}종목)")
    print(f"{'종목명':<28} {'k':>5} {'mfi':>5} {'adx':>5}")
    print("-" * 50)
    for name, p in TICKER_PARAMS.items():
        print(f"{name:<28} {p['k']:>5.1f} {p['mfi']:>5d} {p['adx_threshold']:>5d}")

    # ── Step 2: K200 로드 ────────────────────────────────────────────────────
    print(f"\n[2/3] K200 마스터 + 레짐 판독...")
    k200_raw = fdr.DataReader("069500", start=START_DATE, end=END_DATE)
    if isinstance(k200_raw.columns, pd.MultiIndex):
        k200_raw.columns = k200_raw.columns.get_level_values(0)
    k200_raw.columns = [str(c).lower() for c in k200_raw.columns]
    if 'date' not in k200_raw.columns:
        k200_raw = k200_raw.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
    k200_raw['date'] = pd.to_datetime(k200_raw['date']).dt.strftime('%Y-%m-%d')
    k200_raw = k200_raw.sort_values('date')
    k200_raw = k200_raw[(k200_raw['date'] >= "2019-01-02") & (k200_raw['date'] <= "2026-04-03")]
    k200_raw['mfi'] = calculate_mfi(k200_raw)
    k200_raw['intraday_intensity'] = calculate_intraday_intensity(k200_raw)
    k200_sig = build_signals_and_targets(k200_raw, "KODEX 200", turbo_discount=0.5)
    regime_series = get_market_regime(k200_sig, use_global_mfi=True)
    print(f"  K200: {len(k200_raw)} rows  |  Bull 비율: {regime_series.mean()*100:.1f}%")

    # ── Step 3: 종목별 최적 파라미터 vs 기본값 백테스트 ──────────────────────
    print(f"\n[3/3] 종목별 파라미터 효과 검증 (최적 vs 기본값 비교)")
    print(f"\n{'종목명':<28} {'데이터':>5} {'k':>4} {'mfi':>4} {'adx':>4} "
          f"{'최적수익률':>10} {'기본수익률':>10} {'차이':>8} {'매매수':>6} {'승률':>6} {'상태':>6}")
    print("-" * 100)

    skip_count = 0
    ok_count = 0
    improved_count = 0

    for raw_code, info in ETF_UNIVERSE.items():
        name = info["name"]
        p = TICKER_PARAMS[name]

        result = load_and_prepare(raw_code, name, k200_raw, regime_series)
        if result is None:
            print(f"  {'[DATA<60]':<28} {name}")
            skip_count += 1
            continue

        df_sync, regime_aligned, rows = result

        # 최적 파라미터 백테스트
        opt = backtest_single(df_sync, regime_aligned, name)
        # 기본값(name=DEFAULT이므로 TICKER_PARAMS에 없음 → 기본값 적용)
        dft = backtest_single(df_sync, regime_aligned, "DEFAULT")

        if opt is None or dft is None:
            print(f"  [SKIP-BT] {name}")
            skip_count += 1
            continue

        diff = opt['cumret'] - dft['cumret']
        status = "BETTER" if diff > 0.5 else ("WORSE" if diff < -0.5 else "SAME")
        improved_count += 1 if diff > 0.5 else 0
        ok_count += 1

        print(f"{name:<28} {rows:>5} {p['k']:>4.1f} {p['mfi']:>4d} {p['adx_threshold']:>4d} "
              f"{opt['cumret']:>9.2f}% {dft['cumret']:>9.2f}% {diff:>+8.2f}% "
              f"{opt['trades']:>6} {opt['winrate']:>5.1f}%  {status}")

    # ── 요약 ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f" 요약: 검증완료={ok_count}  데이터부족 스킵={skip_count}  파라미터 개선={improved_count}/{ok_count}")
    print("=" * 80)

    # ── TICKER_PARAMS 체계 무결성 검증 ───────────────────────────────────────
    print("\n[무결성 체크] strategy.build_signals_and_targets TICKER_PARAMS 연동 확인")
    from engine.strategy import TICKER_PARAMS as SP
    mismatch = []
    for name, p in TICKER_PARAMS.items():
        sp = SP.get(name)
        if sp is None:
            mismatch.append(f"  [MISSING] '{name}' strategy.TICKER_PARAMS에 없음")
        elif sp != p:
            mismatch.append(f"  [MISMATCH] '{name}': config={p} / strategy={sp}")
    if mismatch:
        print("  경고:")
        for m in mismatch:
            print(m)
    else:
        print(f"  OK: 15종목 모두 config.etf_universe.TICKER_PARAMS == engine.strategy.TICKER_PARAMS")


if __name__ == "__main__":
    main()
