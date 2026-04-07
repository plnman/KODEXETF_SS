"""
compare_krx_vs_naver.py
========================
FDR(KRX) vs Naver Finance 7년 데이터 비교 검증 스크립트
- 백테스트 대상 22개 ETF 전종목 검증
- 날짜 커버리지, 종가 일치율, 불일치 상세 리포트

실행: python compare_krx_vs_naver.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
import FinanceDataReader as fdr
import requests
import time
from datetime import datetime

# ── 설정 ──────────────────────────────────────────────────────────────
START_DATE  = "2019-01-02"
END_DATE    = "2026-04-04"   # 백테스트 봉인 종료일
PRICE_TOL   = 5              # 종가 허용 오차 (원)
DELAY_SEC   = 0.5            # Naver 요청 간격 (초)

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
    "244580": "KODEX 바이오",
    "315930": "KODEX Top5PlusTR",
}

# ── Naver Finance 스크래퍼 ─────────────────────────────────────────────
def fetch_naver(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Naver Finance 차트 API에서 일별 OHLCV 조회"""
    headers = {"User-Agent": "Mozilla/5.0"}
    url = (
        f"https://fchart.stock.naver.com/sise.nhn"
        f"?symbol={ticker}&timeframe=day&count=3000&requestType=0"
    )
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  [Naver] {ticker} 요청 실패: {e}")
        return pd.DataFrame()

    # 응답 형식: <item data="YYYYMMDD|시|고|저|종|거래량" ... />
    rows = []
    for line in r.text.split("<item"):
        if 'data="' not in line:
            continue
        try:
            data_str = line.split('data="')[1].split('"')[0]
            parts = data_str.split("|")
            if len(parts) < 5:
                continue
            date_str = parts[0]
            close = int(parts[4])
            open_ = int(parts[1])
            high  = int(parts[2])
            low   = int(parts[3])
            vol   = int(parts[5]) if len(parts) > 5 else 0
            rows.append({
                "date":   pd.to_datetime(date_str, format="%Y%m%d").strftime("%Y-%m-%d"),
                "open":   open_,
                "high":   high,
                "low":    low,
                "close":  close,
                "volume": vol,
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    return df


# ── FDR(KRX) 로더 ─────────────────────────────────────────────────────
def fetch_fdr(ticker: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = fdr.DataReader(ticker, start=start, end=end)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        if "date" not in df.columns:
            df = df.reset_index()
            df.rename(columns={"Date": "date", "index": "date"}, inplace=True)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        return df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        print(f"  [FDR] {ticker} 요청 실패: {e}")
        return pd.DataFrame()


# ── 단일 종목 비교 ─────────────────────────────────────────────────────
def compare_ticker(ticker: str, name: str) -> dict:
    print(f"\n[{ticker}] {name}")

    fdr_df   = fetch_fdr(ticker, START_DATE, END_DATE)
    time.sleep(DELAY_SEC)
    naver_df = fetch_naver(ticker, START_DATE, END_DATE)

    result = {
        "ticker": ticker,
        "종목명": name,
        "FDR 행수": len(fdr_df),
        "Naver 행수": len(naver_df),
        "공통 날짜수": 0,
        "종가 완전일치": 0,
        "종가 오차≤5원": 0,
        "불일치 건수": 0,
        "최대 오차(원)": 0,
        "평균 오차(원)": 0.0,
        "판정": "❓",
        "비고": "",
    }

    if fdr_df.empty:
        result["판정"] = "🔴 FDR 실패"
        return result
    if naver_df.empty:
        result["판정"] = "🟡 Naver 실패"
        return result

    # 공통 날짜 병합
    merged = pd.merge(
        fdr_df[["date", "close"]].rename(columns={"close": "fdr_close"}),
        naver_df[["date", "close"]].rename(columns={"close": "nv_close"}),
        on="date", how="inner"
    )
    result["공통 날짜수"] = len(merged)

    if merged.empty:
        result["판정"] = "🔴 공통 날짜 없음"
        return result

    merged["diff"] = (merged["fdr_close"] - merged["nv_close"]).abs()
    exact_match     = (merged["diff"] == 0).sum()
    tol_match       = (merged["diff"] <= PRICE_TOL).sum()
    mismatch        = (merged["diff"] > PRICE_TOL).sum()

    result["종가 완전일치"] = int(exact_match)
    result["종가 오차≤5원"] = int(tol_match)
    result["불일치 건수"]   = int(mismatch)
    result["최대 오차(원)"] = int(merged["diff"].max())
    result["평균 오차(원)"] = round(float(merged["diff"].mean()), 1)

    match_pct = exact_match / len(merged) * 100
    tol_pct   = tol_match   / len(merged) * 100

    if match_pct == 100:
        result["판정"] = "✅ 완전일치"
    elif tol_pct >= 99:
        result["판정"] = "🟢 오차 ≤5원 (99%+)"
    elif tol_pct >= 95:
        result["판정"] = "🟡 일부 오차"
    else:
        result["판정"] = "🔴 불일치 다수"

    # 날짜 커버리지 차이
    fdr_dates   = set(fdr_df["date"])
    naver_dates = set(naver_df["date"])
    only_fdr    = fdr_dates - naver_dates
    only_naver  = naver_dates - fdr_dates
    if only_fdr or only_naver:
        result["비고"] = f"FDR전용:{len(only_fdr)}일 / Naver전용:{len(only_naver)}일"

    print(f"  FDR: {len(fdr_df)}행 | Naver: {len(naver_df)}행 | "
          f"공통: {len(merged)}행 | 완전일치: {exact_match} | 불일치: {mismatch} | {result['판정']}")
    return result


# ── 메인 ───────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print(f"  FDR(KRX) vs Naver Finance 7년 데이터 비교")
    print(f"  기간: {START_DATE} ~ {END_DATE}")
    print(f"  대상: {len(TICKERS)}개 ETF | 종가 허용오차: {PRICE_TOL}원")
    print("=" * 65)

    results = []
    for ticker, name in TICKERS.items():
        r = compare_ticker(ticker, name)
        results.append(r)

    # 요약 리포트
    df = pd.DataFrame(results)
    print("\n" + "=" * 65)
    print("  최종 비교 리포트")
    print("=" * 65)

    cols = ["ticker", "종목명", "FDR 행수", "Naver 행수", "공통 날짜수",
            "종가 완전일치", "불일치 건수", "최대 오차(원)", "판정", "비고"]
    print(df[cols].to_string(index=False))

    # 전체 통계
    total_common   = df["공통 날짜수"].sum()
    total_exact    = df["종가 완전일치"].sum()
    total_mismatch = df["불일치 건수"].sum()
    overall_pct    = total_exact / total_common * 100 if total_common > 0 else 0

    print("\n" + "─" * 65)
    print(f"  전체 공통 데이터포인트 : {total_common:,}건")
    print(f"  완전일치               : {total_exact:,}건 ({overall_pct:.2f}%)")
    print(f"  불일치(>5원)           : {total_mismatch:,}건")
    print(f"  완전일치 종목          : {(df['판정']=='✅ 완전일치').sum()}/{len(df)}개")
    print("─" * 65)

    # CSV 저장
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"tmp/data_comparison_{ts}.csv"
    import os; os.makedirs("tmp", exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n  리포트 저장: {out_path}")

    # 불일치 종목 상세
    bad = df[df["불일치 건수"] > 0]
    if not bad.empty:
        print(f"\n  ⚠️  불일치 발생 종목 ({len(bad)}개):")
        for _, row in bad.iterrows():
            print(f"    [{row['ticker']}] {row['종목명']} "
                  f"불일치 {row['불일치 건수']}건 / 최대오차 {row['최대 오차(원)']}원")
    else:
        print("\n  🎉 모든 종목 데이터 일치 (오차 ≤5원 기준)")

    print("\n  백테스트 신뢰도 결론:")
    if overall_pct >= 99.9:
        print("  ✅ FDR 데이터 신뢰 가능 — 백테스트 결과 유효")
    elif overall_pct >= 99.0:
        print("  🟡 미세 오차 존재 — 백테스트 결과 실질적 영향 없음")
    else:
        print("  🔴 유의미한 불일치 — 데이터 소스 재검토 필요")


if __name__ == "__main__":
    main()
