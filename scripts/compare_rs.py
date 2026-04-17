"""
app.py 방식 vs production 방식 RS 계산 정확 비교
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r'C:\Users\kim.ss\Projects\Claude_KODEX_SS\app')

import pandas as pd
from datetime import datetime, timedelta
import FinanceDataReader as fdr

from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity
from engine.strategy import build_signals_and_targets, get_market_regime
from config.etf_universe import ETFS_CLEAN
from scripts.save_daily_signals import load_ticker, LOOKBACK_DAYS

REVIEW_DATE = '2026-04-17'
start_date  = (datetime.strptime(REVIEW_DATE, '%Y-%m-%d') - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')

# ── 공통: K200 로드 ────────────────────────────────────────────────────────────
def _clean(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    if 'date' not in df.columns: df = df.reset_index().rename(columns={'Date':'date','index':'date'})
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    return df.sort_values('date')

k200 = _clean(fdr.DataReader("069500", start=start_date))
k200['mfi'] = calculate_mfi(k200)
k200['intraday_intensity'] = calculate_intraday_intensity(k200)
k200_sig = build_signals_and_targets(k200, "KODEX 200", turbo_discount=0.5)
regime   = get_market_regime(k200_sig, use_global_mfi=True)
print(f"K200 rows: {len(k200)}, regime last: {bool(regime.iloc[-1])}")

rs_app  = {}   # app.py 방식
rs_prod = {}   # production 방식

for tk, name in ETFS_CLEAN.items():
    fdr_code = tk  # ETFS_CLEAN은 .KS 제거된 코드

    # ── production 방식 (save_daily_signals.py) ─────────────────────────────
    df_p = load_ticker(fdr_code, start=start_date)
    if df_p is None:
        print(f"  [SKIP] {name}")
        continue
    df_p = df_p[df_p['date'] <= pd.Timestamp(REVIEW_DATE)].reset_index(drop=True)
    if len(df_p) < 30:
        print(f"  [SKIP] {name} rows={len(df_p)}")
        continue
    df_p['mfi'] = calculate_mfi(df_p)
    df_p['intraday_intensity'] = calculate_intraday_intensity(df_p)
    regime_p = regime.reindex(df_p.set_index('date').index).fillna(False)   # production: fillna(False)
    sig_p = build_signals_and_targets(df_p.copy(), ticker_name=name, is_bull_market=regime_p, turbo_discount=0.4)
    rs_prod[name] = float(sig_p.iloc[-1]['composite_rs'])

    # ── app.py 방식 ──────────────────────────────────────────────────────────
    df_a = load_ticker(fdr_code, start=start_date)
    if df_a is None: continue
    df_a['mfi'] = calculate_mfi(df_a)
    df_a['intraday_intensity'] = calculate_intraday_intensity(df_a)
    # K200 날짜로 reindex + ffill + fillna(0)
    k200_idx = pd.to_datetime(k200['date'])
    df_a2 = df_a.copy()
    df_a2['date'] = pd.to_datetime(df_a2['date'])
    df_a2 = df_a2.set_index('date')
    df_sync = df_a2.reindex(k200_idx).ffill().fillna(0)
    df_sync.index.name = 'date'
    df_sync = df_sync.copy()
    df_sync['date'] = df_sync.index.astype(str).str[:10]
    df_sync = df_sync.reset_index(drop=True).drop_duplicates(subset=['date'])
    # fillna(True): regime 결측 → 불장 처리
    regime_a = regime.reindex(df_sync.set_index('date').index).fillna(True)
    sig_a = build_signals_and_targets(df_sync.copy(), ticker_name=name, is_bull_market=regime_a, turbo_discount=0.4)
    rs_app[name] = float(sig_a.iloc[-1]['composite_rs'])

# ── 비교 출력 ─────────────────────────────────────────────────────────────────
names_all = sorted(set(rs_prod) | set(rs_app), key=lambda n: rs_prod.get(n, 0), reverse=True)

print(f"\n{'순위':^4} {'종목':<32} {'production RS':>14} {'app RS':>10} {'차이':>8} {'순위변화'}")
print('-' * 80)

rank_prod = {n: i for i, n in enumerate(sorted(rs_prod, key=rs_prod.get, reverse=True), 1)}
rank_app  = {n: i for i, n in enumerate(sorted(rs_app,  key=rs_app.get,  reverse=True), 1)}

for n in sorted(rs_prod, key=rs_prod.get, reverse=True):
    rp = rs_prod.get(n, float('nan'))
    ra = rs_app.get(n, float('nan'))
    diff = ra - rp
    rk_p = rank_prod.get(n, '-')
    rk_a = rank_app.get(n, '-')
    chg  = f"{rk_p}→{rk_a}" if rk_p != rk_a else f"  {rk_p}위  (동일)"
    flag = ' ◀ 순위 다름!' if rk_p != rk_a else ''
    print(f"  {rk_p:^4} {n:<32} {rp:>14.6f} {ra:>10.6f} {diff:>+8.6f}  {chg}{flag}")
