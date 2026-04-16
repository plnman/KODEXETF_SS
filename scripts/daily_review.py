"""
scripts/daily_review.py
========================
매일 전일 실행 결과를 종합 점검하는 영구 검증 스크립트.

실행:
    python scripts/daily_review.py            # 전일 자동 계산
    python scripts/daily_review.py 2026-04-15 # 특정일 지정

원칙:
    - 인위적 함수 재구현 없음
    - 실제 production 코드 함수만 직접 import/사용
    - 매일 동일한 방식으로 실행 가능
"""

import sys
import os
sys.stdout = __import__('io').TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
import pytz

# ── Production 함수만 사용 ────────────────────────────────────────────────────
from data_collector.supabase_client import get_supabase_client
from data_collector.daily_scraper import (
    calculate_mfi,
    calculate_intraday_intensity,
)
from engine.strategy import (
    build_signals_and_targets,
    get_market_regime,
    ATR_MULTIPLIER,
)
from config.etf_universe import TICKER_PARAMS, ETFS_CLEAN
from scripts.save_daily_signals import load_ticker, load_k200_regime, LOOKBACK_DAYS

# ── 날짜 설정 ──────────────────────────────────────────────────────────────────
KST = pytz.timezone('Asia/Seoul')
if len(sys.argv) > 1:
    REVIEW_DATE = sys.argv[1]  # 점검 대상일 (신호 저장일 = 전일)
else:
    REVIEW_DATE = (datetime.now(KST) - timedelta(days=1)).strftime('%Y-%m-%d')
    # 주말이면 금요일로 보정
    d = datetime.strptime(REVIEW_DATE, '%Y-%m-%d')
    if d.weekday() == 5: REVIEW_DATE = (d - timedelta(days=1)).strftime('%Y-%m-%d')
    if d.weekday() == 6: REVIEW_DATE = (d - timedelta(days=2)).strftime('%Y-%m-%d')

# execute_date = REVIEW_DATE 당일 (신호저장 + 체결이 같은 날 16:10 스크립트에서 동시 처리)
EXECUTE_DATE = REVIEW_DATE

sb = get_supabase_client()
SEP = '=' * 65

print(SEP)
print(f" KODEX IRP 일일점검  |  signal_date={REVIEW_DATE}  |  execute_date={EXECUTE_DATE}")
print(SEP)

# ══════════════════════════════════════════════════════════════════════════════
# [1] daily_signals DB 저장 현황
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[1] daily_signals 저장 현황 (signal_date={REVIEW_DATE})")
res = sb.table('daily_signals').select(
    'ticker,composite_rs,close,target_break_price,buy_signal,exit_signal,mfi,hard_stop_loss_pct'
).eq('signal_date', REVIEW_DATE).order('composite_rs', desc=True).execute()
db_rows = {r['ticker']: r for r in (res.data or [])}
skip_expected = {'KODEX 미국AI광통신네트워크', 'KODEX 미국우주항공'}  # 30일 미만 SKIP 종목

print(f"  저장: {len(db_rows)}개  (기대: {len(ETFS_CLEAN) - len(skip_expected)}개, SKIP: {len(skip_expected)}개)")
print(f"  {'순위':<4} {'종목':<32} {'RS':>8} {'종가':>8} {'목표가':>8} {'MFI':>6} {'stop':>6} {'BUY':>5} {'EXIT':>5}")
print(f"  {'-'*82}")
for i, (name, r) in enumerate(sorted(db_rows.items(), key=lambda x: x[1].get('composite_rs', 0), reverse=True), 1):
    buy  = 'BUY'  if r.get('buy_signal')  else ''
    exit_ = 'EXIT' if r.get('exit_signal') else ''
    print(f"  {i:<4} {name:<32} {r.get('composite_rs',0):>8.4f} {r.get('close',0):>8,.0f} "
          f"{r.get('target_break_price',0):>8,.0f} {r.get('mfi',0):>6.1f} "
          f"{r.get('hard_stop_loss_pct',0):>6.4f} {buy:>5} {exit_:>5}")

# ══════════════════════════════════════════════════════════════════════════════
# [2] 실전 재계산 검증 (production 함수 그대로 사용)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[2] 실전 재계산 검증 (build_signals_and_targets 직접 호출)")

# load_k200_regime() = save_daily_signals.py와 100% 동일 함수
# 단, TODAY_STR 기준으로 돌므로 REVIEW_DATE 시점 재현을 위해 직접 구성
start_dt = (datetime.strptime(REVIEW_DATE, '%Y-%m-%d') - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')

k200_raw = fdr.DataReader('069500', start_dt).reset_index()
k200_raw.columns = [c.lower() for c in k200_raw.columns]
if 'date' not in k200_raw.columns:
    k200_raw.rename(columns={'index': 'date'}, inplace=True)
k200_raw['date'] = pd.to_datetime(k200_raw['date'])
k200_raw = k200_raw.sort_values('date').reset_index(drop=True)
# REVIEW_DATE 이하로 필터 (오늘 데이터 제외)
k200_raw = k200_raw[k200_raw['date'] <= pd.Timestamp(REVIEW_DATE)].reset_index(drop=True)
k200_raw['mfi'] = calculate_mfi(k200_raw)
k200_raw['intraday_intensity'] = calculate_intraday_intensity(k200_raw)

# build_signals_and_targets = production 함수 그대로
k200_sig = build_signals_and_targets(k200_raw, ticker_name="KODEX 200", turbo_discount=0.5)
# get_market_regime = production 함수 그대로
regime_series = get_market_regime(k200_sig, use_global_mfi=True)
is_bull = bool(regime_series.iloc[-1])

# K200 불장 상태
last_k = k200_sig.iloc[-1]
adx_mean = k200_sig['adx_14'].rolling(252).mean().iloc[-1]
adx_std  = k200_sig['adx_14'].rolling(252).std().iloc[-1]
z_score  = (last_k['adx_14'] - adx_mean) / adx_std if adx_std else 0

print(f"  K200 레짐: {'불장' if is_bull else '안정장'} (is_bull={is_bull})")
print(f"  ADX={last_k['adx_14']:.2f}, Z-Score={z_score:.4f}, MFI={last_k['mfi']:.2f}")
print(f"  불장 진입 조건: Z>2.0 & MFI>40  |  현재 Z={z_score:.4f} → 진입까지 {2.0-z_score:.2f} 부족")

# TOP 5 종목 재계산 검증
top5 = [name for name, _ in sorted(db_rows.items(), key=lambda x: x[1].get('composite_rs', 0), reverse=True)[:5]]
name_to_code = {v: k for k, v in ETFS_CLEAN.items()}

print(f"\n  {'종목':<32} {'DB종가':>8} {'재계산종가':>10} {'DB목표가':>9} {'재계산목표가':>12} {'RS일치':>7} {'목표가일치':>9}")
print(f"  {'-'*95}")

calc_signals = {}
for name in top5:
    code = name_to_code.get(name)
    if not code:
        continue
    # load_ticker = save_daily_signals.py의 production 함수 그대로
    df_t = load_ticker(code, start=start_dt)
    if df_t is None:
        print(f"  {name:<32} [로드 실패]")
        continue
    # REVIEW_DATE 이하로 필터 (오늘 데이터 제외 — 과거 날짜 재현)
    df_t = df_t[df_t['date'] <= pd.Timestamp(REVIEW_DATE)].reset_index(drop=True)
    if len(df_t) < 30:
        print(f"  {name:<32} [데이터 부족 {len(df_t)}행]")
        continue
    df_t['mfi'] = calculate_mfi(df_t)
    df_t['intraday_intensity'] = calculate_intraday_intensity(df_t)

    df_t_idx = df_t.set_index('date')
    regime_al = regime_series.reindex(df_t_idx.index).fillna(False)

    # build_signals_and_targets = production 함수 그대로
    sig = build_signals_and_targets(
        df_t.copy(), ticker_name=name,
        is_bull_market=regime_al,
        turbo_discount=0.4
    )
    last_s = sig.iloc[-1]
    calc_signals[name] = last_s

    db_r = db_rows.get(name, {})
    db_close  = db_r.get('close', 0)
    db_target = db_r.get('target_break_price', 0)
    calc_close  = float(last_s['close'])
    calc_target = float(last_s['target_break_price'])
    rs_ok  = abs(db_r.get('composite_rs', 0) - float(last_s['composite_rs'])) < 0.001
    tgt_ok = abs(db_target - calc_target) < 1.0

    print(f"  {name:<32} {db_close:>8,.0f} {calc_close:>10,.0f} {db_target:>9,.0f} {calc_target:>12,.0f} "
          f"{'[OK]' if rs_ok else '[NG]':>7} {'[OK]' if tgt_ok else '[NG]':>9}")

# 조건 판단 c1~c4 검증
print(f"\n  조건판단 c1~c4 검증 (buy_signal DB vs 재계산)")
print(f"  {'종목':<32} {'c1가격':^6} {'c2MFI':^6} {'c3II':^6} {'c4ADX':^6} {'통과':^5} {'DB':^7} {'일치':^6}")
print(f"  {'-'*82}")
for name in top5:
    if name not in calc_signals:
        continue
    last_s = calc_signals[name]
    params  = TICKER_PARAMS.get(name, {'k': 0.5, 'mfi': 50, 'adx_threshold': 15})
    c1 = float(last_s['close'])             > float(last_s['target_break_price'])
    c2 = float(last_s.get('mfi', 0))       > params['mfi']
    c3 = float(last_s.get('intraday_intensity', 0)) > 0
    c4 = float(last_s.get('adx_14', 0))    > params['adx_threshold']
    passed   = sum([c1, c2, c3, c4])
    buy_calc = (passed == 4)
    buy_db   = bool(db_rows.get(name, {}).get('buy_signal', False))
    match    = (buy_calc == buy_db)
    print(f"  {name:<32} {'O' if c1 else 'X':^6} {'O' if c2 else 'X':^6} {'O' if c3 else 'X':^6} {'O' if c4 else 'X':^6} "
          f"{passed:^5}/4 {str(buy_db):^7} {'[OK]' if match else '[NG]***':^6}")
    print(f"       종가={float(last_s['close']):,.0f} vs 목표={float(last_s['target_break_price']):,.0f} | "
          f"MFI={float(last_s.get('mfi',0)):.1f}>{params['mfi']} | "
          f"II={float(last_s.get('intraday_intensity',0)):.0f} | "
          f"ADX={float(last_s.get('adx_14',0)):.1f}>{params['adx_threshold']}")

# exit_signal 검증
print(f"\n  exit_signal 검증 (안정장: vol_rank<0.3 -> SMA10, else -> SMA20 / 불장: SMA5)")
print(f"  {'종목':<32} {'exit_DB':^8} {'vol_rank':>9} {'SMA기준':^8} {'종가':>8} {'SMA값':>8} {'이탈':>6} {'일치':^6}")
print(f"  {'-'*90}")
for name in top5:
    if name not in calc_signals:
        continue
    last_s  = calc_signals[name]
    exit_db = bool(db_rows.get(name, {}).get('exit_signal', False))
    vr   = float(last_s.get('vol_rank', 0.5) or 0.5)
    curr = float(last_s['close'])
    bull_s = bool(last_s.get('is_bull_market', False))
    if bull_s:
        sma_l, sma_v = 'SMA5',  float(last_s.get('sma_5',  0))
    elif vr < 0.3:
        sma_l, sma_v = 'SMA10', float(last_s.get('sma_10', 0))
    else:
        sma_l, sma_v = 'SMA20', float(last_s.get('sma_20', 0))
    ital  = curr < sma_v
    match = (ital == exit_db)
    print(f"  {name:<32} {str(exit_db):^8} {vr:>9.3f} {sma_l:^8} {curr:>8,.0f} {sma_v:>8,.0f} {str(ital):>6} {'[OK]' if match else '[NG]***':^6}")

# hard_stop_loss_pct 검증 (ATR_MULTIPLIER = production 상수 그대로)
print(f"\n  hard_stop_loss_pct 검증 (ATR_MULTIPLIER={ATR_MULTIPLIER})")
print(f"  공식: atr_14[t-1] * {ATR_MULTIPLIER} / close[t-1]")
print(f"  {'종목':<32} {'DB stop':>9} {'재계산':>9} {'일치':^6}")
print(f"  {'-'*60}")
for name in top5:
    if name not in calc_signals:
        continue
    last_s   = calc_signals[name]
    db_stop  = float(db_rows.get(name, {}).get('hard_stop_loss_pct', 0))
    calc_stop = float(last_s.get('hard_stop_loss_pct', 0))
    match = abs(db_stop - calc_stop) < 0.001
    print(f"  {name:<32} {db_stop:>9.4f} {calc_stop:>9.4f} {'[OK]' if match else '[NG]***':^6}")

# ══════════════════════════════════════════════════════════════════════════════
# [3] live_trades 체결 내역 (execute_date)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[3] live_trades 체결 내역 (execute_date={EXECUTE_DATE})")
res2 = sb.table('live_trades').select('*').eq('execute_date', EXECUTE_DATE).execute()
trades = res2.data or []
if not trades:
    print("  체결 없음")
else:
    for r in trades:
        price = r.get('execute_price', 0)
        units = r.get('units', 0)
        stop  = r.get('hard_stop_pct', 0)
        amt   = price * units
        action = r['action']
        print(f"  {action:<5} {r['ticker']:<32} 단가={price:>8,.0f}원 x {units:.2f}주 = {amt:>14,.0f}원")
        if action == 'BUY':
            # Full Cash Sweep 검증: invest = cash_before_trade * 0.998
            # 체결 전 현금 = 전일(REVIEW_DATE - 1 거래일) portfolio_history cash
            signal_date_for_trade = (datetime.strptime(REVIEW_DATE, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            d_sig = datetime.strptime(signal_date_for_trade, '%Y-%m-%d')
            if d_sig.weekday() == 5: signal_date_for_trade = (d_sig - timedelta(days=1)).strftime('%Y-%m-%d')
            if d_sig.weekday() == 6: signal_date_for_trade = (d_sig - timedelta(days=2)).strftime('%Y-%m-%d')
            res_port = sb.table('live_portfolio_history').select('cash').eq('date', signal_date_for_trade).execute()
            prev_cash = res_port.data[0]['cash'] if res_port.data else None
            if prev_cash:
                expected = prev_cash * 0.998
                match_fs = abs(amt - expected) < 5000
                print(f"         Full Cash Sweep 검증: cash({signal_date_for_trade})={prev_cash:,.0f} x 0.998 = {expected:,.0f}  -> {'[OK]' if match_fs else '[NG]***'}")
            print(f"         hard_stop_pct={stop:.4f}  =>  하드스탑가={price*(1-stop):,.0f}원")

# ══════════════════════════════════════════════════════════════════════════════
# [4] live_portfolio_history
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[4] live_portfolio_history (최근 5일)")
res3 = sb.table('live_portfolio_history').select('*').order('date', desc=True).limit(5).execute()
print(f"  {'날짜':<12} {'현금':>14} {'보유평가':>14} {'총계':>14} {'수익률':>9}")
print(f"  {'-'*65}")
for r in (res3.data or []):
    print(f"  {r.get('date',''):<12} {r.get('cash',0):>14,.0f} {r.get('holdings_value',0):>14,.0f} "
          f"{r.get('total_value',0):>14,.0f} {r.get('return_pct',0):>+9.4f}%")

# ══════════════════════════════════════════════════════════════════════════════
# [5] 현재 보유 포지션
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[5] 현재 보유 포지션")
res4 = sb.table('live_trades').select('ticker,action,execute_price,units,hard_stop_pct,execute_date').execute()
pos = {}
for r in (res4.data or []):
    tk = r['ticker']
    if r['action'] == 'BUY':
        pos[tk] = r
    elif r['action'] == 'EXIT':
        pos.pop(tk, None)
if not pos:
    print("  보유 없음")
else:
    print(f"  {'종목':<32} {'진입일':<12} {'진입가':>8} {'수량':>8} {'stop':>7} {'하드스탑가':>10}")
    print(f"  {'-'*80}")
    for tk, r in pos.items():
        ep    = r.get('execute_price', 0)
        units = r.get('units', 0)
        stop  = r.get('hard_stop_pct', 0)
        print(f"  {tk:<32} {r.get('execute_date',''):<12} {ep:>8,.0f} {units:>8.2f} {stop:>7.4f} {ep*(1-stop):>10,.0f}")

# ══════════════════════════════════════════════════════════════════════════════
# [6] RS 전체 순위 (15종목)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[6] RS 전체 순위 ({REVIEW_DATE})")
all_rs = sorted(db_rows.items(), key=lambda x: x[1].get('composite_rs', 0), reverse=True)
print(f"  {'순위':<4} {'종목':<32} {'RS':>8}  {'TOP5카드'}")
for i, (name, r) in enumerate(all_rs, 1):
    mark = '<-- 카드 표시' if i <= 5 else ''
    print(f"  {i:<4} {name:<32} {r.get('composite_rs',0):>8.4f}  {mark}")

# ══════════════════════════════════════════════════════════════════════════════
# [7] 종합 판정
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print(" 종합 판정")
print(SEP)
expected_cnt = len(ETFS_CLEAN) - len(skip_expected)
cnt_ok   = len(db_rows) == expected_cnt
print(f"  [1] 신호 저장 수:   {'[OK]' if cnt_ok else '[NG]'} ({len(db_rows)}/{expected_cnt})")
print(f"  [2] 재계산 일치:    위 섹션에서 [NG]*** 항목 없으면 [OK]")
print(f"  [3] 체결 내역:      {'있음 '+str(len(trades))+'건' if trades else '없음'}")
print(f"  K200 레짐:          {'불장' if is_bull else '안정장'} (Z={z_score:.3f})")
print(f"  turbo_discount=0.4: {'활성 (불장중)' if is_bull else '대기중 (안정장)'}")
print(SEP)
