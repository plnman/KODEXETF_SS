"""
param_optimizer.py
==================
파라미터 조정값별 / 연도별 수익률 비교 분석
- 파라미터 1개씩 변경 (ceteris paribus) → 효과 명확히 분리
- Baseline(현재값)이 362.84%와 일치하는지 코드 무결성 검증
- 연도별 수익률 + 누적 수익률 테이블 출력

실행: cd KODEXETF_SS && python param_optimizer.py
"""
import sys, io, os, pickle, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
import FinanceDataReader as fdr
from copy import deepcopy

from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity
from analytics.portfolio_backtester import run_portfolio_backtest
import engine.strategy as strategy
from engine.strategy import TICKER_PARAMS, build_signals_and_targets

# ── 설정 ──────────────────────────────────────────────────────────────
START_DATE    = "2019-01-02"
END_DATE      = "2026-04-04"
INITIAL_CAP   = 50_000_000.0
MAX_TICKERS   = 5
BASELINE_ROI  = 472.66       # 무결성 기준값 (V3.6.0: ATR=2.5 채택 후 갱신)
CACHE_FILE    = "tmp/raw_data_cache.pkl"

TICKERS = {
    "069500": "KODEX 200",
    "226490": "KODEX 코스닥150",
    "091160": "KODEX 반도체",
    "091170": "KODEX 은행",
    "091180": "KODEX 자동차",
    "305720": "KODEX 2차전지산업",
    "117700": "KODEX 건설",
    "091220": "KODEX 금융",
    "102970": "KODEX 기계장비",
    "117680": "KODEX 철강",
    "379800": "KODEX 미국S&P500TR",
    "367380": "KODEX 미국나스닥100TR",
    "314250": "KODEX 미국FANG플러스(H)",
    "315270": "KODEX 미국산업재(합성)",
    "251350": "KODEX 선진국MSCI World",
    "475380": "KODEX 글로벌AI인프라",
    "453850": "KODEX 인도Nifty50",
    "465610": "KODEX 미국반도체MV",
    "461580": "KODEX 미국배당프리미엄액티브",
    "0080G0": "KODEX K방산TOP10",
    "244580": "KODEX 바이오",
    "315930": "KODEX Top5PlusTR",
    # [NEW] V3.6.0 편입
    "487240": "KODEX AI전력핵심설비",
}

# ── 테스트 파라미터 세트 ──────────────────────────────────────────────
# (label, turbo_discount, atr_multiplier, z_bull, z_stable, mfi_regime, k_scale)
# 현재값: turbo=0.4, atr=3.0, z_bull=2.0, z_stable=1.0, mfi=40, k_scale=1.0
PARAM_SETS = [
    ("★ Baseline (현재)", 0.4, 3.0, 2.0, 1.0, 40, 1.0),
    # Turbo K 변경
    ("Turbo K=0.3",       0.3, 3.0, 2.0, 1.0, 40, 1.0),
    ("Turbo K=0.5",       0.5, 3.0, 2.0, 1.0, 40, 1.0),
    # ATR 스탑로스 배수
    ("ATR=2.0",           0.4, 2.0, 2.0, 1.0, 40, 1.0),
    ("ATR=2.5",           0.4, 2.5, 2.0, 1.0, 40, 1.0),
    ("ATR=3.5",           0.4, 3.5, 2.0, 1.0, 40, 1.0),
    # Regime Z_Bull 임계값
    ("Z_Bull=1.5",        0.4, 3.0, 1.5, 1.0, 40, 1.0),
    ("Z_Bull=2.5",        0.4, 3.0, 2.5, 1.0, 40, 1.0),
    # Regime MFI 필터
    ("MFI_Regime=30",     0.4, 3.0, 2.0, 1.0, 30, 1.0),
    ("MFI_Regime=50",     0.4, 3.0, 2.0, 1.0, 50, 1.0),
    # K_base 전체 스케일 (전 종목 K값 일괄 조정)
    ("K_scale=0.7x",      0.4, 3.0, 2.0, 1.0, 40, 0.7),
    ("K_scale=1.3x",      0.4, 3.0, 2.0, 1.0, 40, 1.3),
]

YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

# ── 데이터 로딩 (캐시 우선) ───────────────────────────────────────────
def load_raw_data():
    os.makedirs("tmp", exist_ok=True)
    if os.path.exists(CACHE_FILE):
        print(f"  캐시 로드: {CACHE_FILE}")
        with open(CACHE_FILE, "rb") as f:
            return pickle.load(f)

    print(f"  FDR에서 {len(TICKERS)}개 종목 다운로드 중...")
    raw = {}
    for i, (tk, name) in enumerate(TICKERS.items()):
        print(f"    [{i+1}/{len(TICKERS)}] {name}...", end=" ")
        try:
            df = fdr.DataReader(tk, start=START_DATE, end=END_DATE)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            if 'date' not in df.columns:
                df = df.reset_index()
                df.rename(columns={'Date':'date','index':'date'}, inplace=True)
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)]
            df = df.sort_values('date').reset_index(drop=True)
            df['mfi'] = calculate_mfi(df)
            df['intraday_intensity'] = calculate_intraday_intensity(df)
            raw[name] = df
            print(f"OK ({len(df)}행)")
        except Exception as e:
            print(f"FAIL ({e})")
        time.sleep(0.2)

    with open(CACHE_FILE, "wb") as f:
        pickle.dump(raw, f)
    print(f"  캐시 저장 완료: {CACHE_FILE}")
    return raw


# ── 파라미터화된 레짐 판단 ────────────────────────────────────────────
def get_regime_parameterized(market_df, z_bull=2.0, z_stable=1.0, mfi_regime=40):
    df = market_df.copy()
    adx_mean = df['adx_14'].rolling(252).mean()
    adx_std  = df['adx_14'].rolling(252).std()
    z_score  = (df['adx_14'] - adx_mean) / adx_std

    regime, curr = [], False
    for i, z in enumerate(z_score):
        if pd.isna(z):
            regime.append(False)
            continue
        mfi_ok = df['mfi'].iloc[i] > mfi_regime if 'mfi' in df.columns else True
        if not curr and z > z_bull and mfi_ok:
            curr = True
        elif curr and z < z_stable:
            curr = False
        regime.append(curr)
    return pd.Series(regime, index=df.index)


# ── 단일 파라미터 세트로 백테스트 실행 ───────────────────────────────
def run_with_params(raw_data, turbo_discount, atr_multiplier,
                    z_bull, z_stable, mfi_regime, k_scale):
    # ATR_MULTIPLIER 동적 패치
    strategy.ATR_MULTIPLIER = atr_multiplier

    k200_raw = raw_data.get("KODEX 200")
    if k200_raw is None:
        return None

    # KODEX200 신호 생성 (레짐 판단용)
    k200_sig = build_signals_and_targets(
        k200_raw, "KODEX 200", turbo_discount=0.5
    )
    regime = get_regime_parameterized(k200_sig, z_bull, z_stable, mfi_regime)

    # 전 종목 신호 생성
    all_signals = {}
    k200_dates = set(k200_raw['date'])

    for name, df in raw_data.items():
        # K_scale 적용: 종목 파라미터 오버라이드
        orig_params = TICKER_PARAMS.get(name, {'k': 0.5, 'mfi': 60, 'adx_threshold': 20})
        scaled_k = max(0.1, min(orig_params['k'] * k_scale, 0.9))
        overrides = {'k': scaled_k}

        # KODEX200 날짜 축으로 동기화
        df_sync = (df.set_index('date')
                     .reindex(k200_raw.set_index('date').index)
                     .reset_index()
                     .ffill()
                     .fillna(0))
        df_sync = df_sync.drop_duplicates(subset=['date'])

        regime_aligned = regime.reindex(
            df_sync.set_index('date').index
        ).fillna(False)

        sig = build_signals_and_targets(
            df_sync,
            ticker_name=name,
            overrides=overrides,
            is_bull_market=regime_aligned,
            turbo_discount=turbo_discount
        )
        all_signals[name] = sig

    # 포트폴리오 백테스트
    result = run_portfolio_backtest(
        all_signals, INITIAL_CAP, MAX_TICKERS, use_cash_sweep=True
    )

    # ATR_MULTIPLIER 원복
    strategy.ATR_MULTIPLIER = 3.0
    return result


# ── 연도별 수익률 추출 ────────────────────────────────────────────────
def extract_annual_returns(history_df):
    if history_df is None or history_df.empty:
        return {}

    df = history_df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()

    annual = {}
    prev_val = INITIAL_CAP

    for year in YEARS:
        yr_data = df[df.index.year == year]
        if yr_data.empty:
            continue
        end_val = yr_data['total_value'].iloc[-1]
        ret = (end_val / prev_val - 1) * 100
        annual[year] = round(ret, 2)
        prev_val = end_val

    return annual


# ── 메인 ─────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  파라미터 최적화 분석 — 연도별 수익률 비교")
    print(f"  기간: {START_DATE} ~ {END_DATE} | 초기자본: {INITIAL_CAP:,.0f}원 | {MAX_TICKERS}종목")
    print("=" * 70)

    print("\n[1] 데이터 로딩")
    raw_data = load_raw_data()
    print(f"  로드 완료: {len(raw_data)}개 종목\n")

    results = []
    integrity_ok = None

    print("[2] 파라미터별 백테스트 실행")
    for i, (label, turbo_k, atr_mult, z_bull, z_stable, mfi_regime, k_scale) in enumerate(PARAM_SETS):
        print(f"  [{i+1:02d}/{len(PARAM_SETS)}] {label}...", end=" ", flush=True)
        t0 = time.time()

        result = run_with_params(
            raw_data, turbo_k, atr_mult, z_bull, z_stable, mfi_regime, k_scale
        )

        elapsed = time.time() - t0
        if result is None:
            print("FAIL")
            continue

        total_ret  = result['cumulative_return']
        cagr       = result['cagr']
        mdd        = result['mdd']
        annual     = extract_annual_returns(result['history'])
        trades_df  = result.get('trades_df', pd.DataFrame())
        n_trades   = len(trades_df)
        n_win      = int((trades_df['수익률(%)'] > 0).sum()) if not trades_df.empty else 0
        win_rate   = round(n_win / n_trades * 100, 1) if n_trades > 0 else 0
        avg_ret    = round(trades_df['수익률(%)'].mean(), 2) if not trades_df.empty else 0
        stop_cnt   = int(trades_df['매매사유'].str.contains('Hard Stop').sum()) if not trades_df.empty else 0

        # Baseline 무결성 검증
        is_baseline = label.startswith("★")
        integrity_flag = ""
        if is_baseline:
            diff = abs(total_ret - BASELINE_ROI)
            if diff < 0.1:
                integrity_flag = " ✅ 무결성 OK"
                integrity_ok = True
            else:
                integrity_flag = f" ❌ 무결성 실패! (기준:{BASELINE_ROI}% vs 실행:{total_ret}%)"
                integrity_ok = False

        print(f"누적: {total_ret:+.2f}% | CAGR: {cagr:.1f}% | MDD: {mdd:.1f}% | "
              f"거래: {n_trades}회 | 승률: {win_rate}% | 손절: {stop_cnt}회 | {elapsed:.1f}s{integrity_flag}")

        row = {
            "파라미터": label,
            "누적(%)": round(total_ret, 2),
            "CAGR(%)": round(cagr, 2),
            "MDD(%)": round(mdd, 2),
            "거래횟수": n_trades,
            "승률(%)": win_rate,
            "평균수익(%)": avg_ret,
            "손절횟수": stop_cnt,
        }
        for y in YEARS:
            row[f"{y}년(%)"] = annual.get(y, "-")
        results.append(row)

    # ── 결과 테이블 출력 ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  [3] 최종 결과 테이블")
    print("=" * 70)

    df_result = pd.DataFrame(results)

    # 콘솔 출력 (기본 지표)
    summary_cols = ["파라미터", "누적(%)", "CAGR(%)", "MDD(%)", "거래횟수", "승률(%)", "평균수익(%)", "손절횟수"]
    year_cols    = [f"{y}년(%)" for y in YEARS if f"{y}년(%)" in df_result.columns]

    print("\n▶ 요약 지표")
    print(df_result[summary_cols].to_string(index=False))

    print("\n▶ 연도별 수익률")
    print(df_result[["파라미터"] + year_cols].to_string(index=False))

    # ── 무결성 결론 ──────────────────────────────────────────────────
    print("\n" + "─" * 70)
    if integrity_ok is True:
        print(f"  ✅ 코드 무결성 검증 통과: Baseline = {BASELINE_ROI}% 재현 성공")
    elif integrity_ok is False:
        print(f"  ❌ 코드 무결성 검증 실패: 결과값 불일치 — 분석 결과 신뢰 불가")
    print("─" * 70)

    # ── 최적 파라미터 추천 ───────────────────────────────────────────
    if integrity_ok:
        best_idx  = df_result["누적(%)"].idxmax()
        best_row  = df_result.iloc[best_idx]
        worst_idx = df_result["누적(%)"].idxmin()
        worst_row = df_result.iloc[worst_idx]

        print(f"\n  🏆 최고 누적 수익: {best_row['파라미터']}  →  {best_row['누적(%)']}%")
        print(f"  💔 최저 누적 수익: {worst_row['파라미터']}  →  {worst_row['누적(%)']}%")

        # 현재 대비 개선 여부
        baseline_ret = df_result.loc[df_result["파라미터"].str.startswith("★"), "누적(%)"].values[0]
        if best_row['누적(%)'] > baseline_ret + 1.0:
            print(f"\n  ⚡ 개선 여지 있음: {best_row['파라미터']} 적용 시 +{best_row['누적(%)'] - baseline_ret:.2f}%p 추가 가능")
        else:
            print(f"\n  ✅ 현재 파라미터가 최적에 가까움 (최선 대비 차이 ≤1%p)")

    # ── CSV 저장 ─────────────────────────────────────────────────────
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"tmp/param_optimization_{ts}.csv"
    df_result.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"\n  결과 저장: {out}")


if __name__ == "__main__":
    main()
