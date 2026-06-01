"""
scripts/save_daily_signals.py
==============================
매일 16:10 KST (07:10 UTC) GitHub Actions에 의해 자동 실행.

[TASK 0] 티커 무결성 검증
[TASK 1] 오늘 신호 기록
  - 전체 15개 ETF 실전 신호 계산 → Supabase daily_signals 저장
  - K200 레짐 기반 is_bull_market 동적 계산 (백테스팅과 동일)
  - turbo_discount=0.4 (백테스팅과 동일)
  - hard_stop_loss_pct 저장

[TASK 2] 전날 신호 체결 기록 (V3.9.0)
  - 전날 신호 조회 → RS 순위 계산
  - EXIT 처리: Hard Stop > Switching(RS 이탈) > SMA 이탈 순서
  - BUY 처리: Full Cash Sweep (잔여현금 × 0.998) — 백테스팅과 동일
  - hard_stop_pct live_trades에 저장

[TASK 3] 포트폴리오 가치 업데이트
  - 현재 보유 포지션 × 오늘 종가 + 현금 = 총 가치
  - live_portfolio_history 저장

실행: python scripts/save_daily_signals.py
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, timedelta
import pytz

from dotenv import load_dotenv
load_dotenv()

import FinanceDataReader as fdr
from supabase import create_client

from data_collector.daily_scraper import (
    calculate_mfi,
    calculate_intraday_intensity,
    TARGET_ETFS,
    verify_tickers,
)
from engine.strategy import build_signals_and_targets, get_market_regime

# ── 설정 ──────────────────────────────────────────────────────────────────────
LOOKBACK_DAYS    = 500
INITIAL_CAPITAL  = 50_000_000.0
SWITCH_THRESHOLD = 10                # RS TOP N 이탈 시 EXIT — 백테스팅 확정값 (수익률 513.34%)
MAX_POSITIONS    = 1                 # 실전 최대 보유 종목 수 — 몰빵 설계 (잔돈 매수 차단)
KST              = pytz.timezone('Asia/Seoul')
now_kst          = datetime.now(KST)
TODAY_STR        = now_kst.strftime("%Y-%m-%d")
# 직전 거래일 계산 (월요일→금요일, 토/일→금요일 보정)
_prev = now_kst - timedelta(days=1)
if _prev.weekday() == 6:    # 일요일 → 금요일
    _prev = _prev - timedelta(days=2)
elif _prev.weekday() == 5:  # 토요일 → 금요일
    _prev = _prev - timedelta(days=1)
YESTERDAY_STR    = _prev.strftime("%Y-%m-%d")

# ── Supabase 연결 ──────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERROR] SUPABASE_URL / SUPABASE_KEY 환경변수 없음. 종료.")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# FDR 티커 역매핑 (.KS 제거)
FDR_CODE = {v: k.replace(".KS", "") for k, v in TARGET_ETFS.items()}


# ── 공통: FDR 데이터 로드 ──────────────────────────────────────────────────────
def load_ticker(fdr_code: str, start: str = None) -> pd.DataFrame | None:
    if start is None:
        start = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    try:
        df = fdr.DataReader(fdr_code, start)
        if df.empty or len(df) < 30:
            return None
        df = df.reset_index().rename(columns={
            'Date': 'date', 'Open': 'open', 'High': 'high',
            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
        })
        df.columns = [c.lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date').reset_index(drop=True)
    except Exception as e:
        print(f"  [WARN] {fdr_code} 로드 실패: {e}")
        return None


# ── K200 레짐 계산 (백테스팅과 동일 로직) ──────────────────────────────────────
def load_k200_regime():
    """K200 기반 시장 레짐 계산. (regime_series, is_bull_now) 반환"""
    start = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    try:
        df = fdr.DataReader("069500", start)
        if df.empty:
            return None, False
        df = df.reset_index().rename(columns={
            'Date': 'date', 'Open': 'open', 'High': 'high',
            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
        })
        df.columns = [c.lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        k200_sig = build_signals_and_targets(df, ticker_name="KODEX 200", turbo_discount=0.5)
        regime_series = get_market_regime(k200_sig, use_global_mfi=True)
        is_bull_now = bool(regime_series.iloc[-1]) if not regime_series.empty else False
        print(f"  K200 레짐: {'🚀 불장' if is_bull_now else '🛡️ 안정장'}")
        return regime_series, is_bull_now
    except Exception as e:
        print(f"  [WARN] K200 레짐 계산 실패: {e} — is_bull_market=False 고정")
        return None, False


# ── TASK 1: 오늘 신호 기록 ────────────────────────────────────────────────────
def task1_save_signals():
    print(f"\n[TASK 1] 신호 기록 — signal_date={TODAY_STR}")

    # K200 레짐 계산
    regime_series, is_bull_now = load_k200_regime()

    success, fail = 0, 0
    all_today_signals = {}   # ticker_name → latest row (TASK 3에서 재사용)

    for ks_code, ticker_name in TARGET_ETFS.items():
        fdr_code = ks_code.replace(".KS", "")
        print(f"  [{fdr_code}] {ticker_name} ...", end=" ")

        df = load_ticker(fdr_code)
        if df is None:
            print("SKIP")
            fail += 1
            continue

        df['mfi']                = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)

        try:
            # regime_series를 날짜 인덱스에 맞춰 정렬 (백테스팅과 동일)
            if regime_series is not None:
                df_indexed = df.set_index('date')
                regime_aligned = regime_series.reindex(df_indexed.index).fillna(False)
            else:
                regime_aligned = False

            sig    = build_signals_and_targets(
                df.copy(),
                ticker_name=ticker_name,
                is_bull_market=regime_aligned,
                turbo_discount=0.4      # 백테스팅과 동일
            )
            latest = sig.iloc[-1]
            all_today_signals[ticker_name] = latest

            record = {
                "signal_date":        TODAY_STR,
                "ticker":             ticker_name,
                "close":              float(latest.get('close', 0)),
                "target_break_price": float(latest.get('target_break_price', 0)),
                "composite_rs":       float(latest.get('composite_rs', 0)),
                "buy_signal":         bool(latest.get('buy_signal_T', False)),
                "exit_signal":        bool(latest.get('exit_signal_T', False)),
                "mfi":                float(latest.get('mfi', 0)),
                "hard_stop_loss_pct": float(latest.get('hard_stop_loss_pct', 0)),
            }
            sb.table('daily_signals').upsert(record, on_conflict='signal_date,ticker').execute()
            mark = "BUY" if record['buy_signal'] else ("EXIT" if record['exit_signal'] else "---")
            print(f"OK [{mark}]")
            success += 1
        except Exception as e:
            print(f"ERROR: {e}")
            fail += 1

    print(f"  → 성공={success} 실패={fail}  불장={is_bull_now}")
    return all_today_signals


# ── TASK 2: 전날 신호 → 오늘 시가로 체결 기록 ────────────────────────────────
def task2_record_executions():
    print(f"\n[TASK 2] 체결 기록 — signal_date={YESTERDAY_STR}, execute_date={TODAY_STR}")

    # 전날 신호 조회
    try:
        res = sb.table('daily_signals').select('*').eq('signal_date', YESTERDAY_STR).execute()
    except Exception as e:
        print(f"  [ERROR] 전날 신호 조회 실패: {e}")
        return

    if not res.data:
        print(f"  전날({YESTERDAY_STR}) 신호 없음 — 스킵")
        return

    all_signals_list = res.data

    # RS 순위 계산 (전날 신호 기준)
    rs_sorted = sorted(all_signals_list, key=lambda x: float(x.get('composite_rs') or 0), reverse=True)
    top_n_tickers = {r['ticker'] for r in rs_sorted[:SWITCH_THRESHOLD]}

    # BUY 후보: RS 내림차순, EXIT 후보: 전체
    buy_candidates  = [r for r in rs_sorted if r.get('buy_signal')]
    exit_signal_tickers = {r['ticker'] for r in all_signals_list if r.get('exit_signal')}

    # 현재 보유 포지션 조회 (entry_price + hard_stop_pct 포함)
    open_positions = _get_open_positions()
    print(f"  현재 보유: {list(open_positions.keys())}")

    # 잔여 현금 추적 (Full Cash Sweep용)
    cash = _calc_cash()
    print(f"  현재 현금: {cash:,.0f}원")

    # 오늘 OHLCV 캐시 (ticker_name → row)
    today_ohlcv = {}
    needed_tickers = set(open_positions.keys()) | {r['ticker'] for r in buy_candidates}
    for ticker_name in needed_tickers:
        fdr_code = FDR_CODE.get(ticker_name)
        if not fdr_code:
            continue
        recent_start = (now_kst - timedelta(days=60)).strftime("%Y-%m-%d")
        df_recent = load_ticker(fdr_code, start=recent_start)
        if df_recent is None or df_recent.empty:
            continue
        today_row = df_recent[df_recent['date'].dt.strftime('%Y-%m-%d') == TODAY_STR]
        if today_row.empty:
            continue
        today_ohlcv[ticker_name] = today_row.iloc[0]

    # ── EXIT 처리 (Hard Stop > Switching > SMA 순서) ──────────────────────────
    tickers_exited = set()
    for ticker_name, pos in list(open_positions.items()):
        if ticker_name not in today_ohlcv:
            print(f"  [SKIP] {ticker_name}: 오늘 데이터 없음 (EXIT 불가)")
            continue

        row       = today_ohlcv[ticker_name]
        units     = pos['units']
        entry_p   = pos['entry_price']
        stop_pct  = pos['hard_stop_pct']
        today_low = float(row['low'])
        today_open = float(row['open'])

        exit_price  = None
        exit_action = None

        # 1) Hard Stop: 오늘 저가가 손절가 이하
        if stop_pct > 0 and entry_p > 0:
            hard_stop_price = entry_p * (1 - stop_pct)
            if today_low <= hard_stop_price:
                exit_price  = hard_stop_price
                exit_action = "EXIT_HARDSTOP"

        # 2) Switching: RS 순위 이탈
        if exit_price is None and ticker_name not in top_n_tickers:
            exit_price  = today_open
            exit_action = "EXIT_SWITCH"

        # 3) SMA 이탈 exit_signal
        if exit_price is None and ticker_name in exit_signal_tickers:
            exit_price  = today_open
            exit_action = "EXIT"

        if exit_price is not None and exit_action is not None:
            amount = round(units * exit_price, 2)
            try:
                _upsert_trade(sb, {
                    "signal_date":   YESTERDAY_STR,
                    "execute_date":  TODAY_STR,
                    "ticker":        ticker_name,
                    "action":        exit_action,
                    "execute_price": exit_price,
                    "signal_close":  float(today_ohlcv[ticker_name]['close']),
                    "units":         float(int(units)),
                    "amount":        amount,
                    "hard_stop_pct": round(stop_pct, 6),
                })
                cash += amount
                tickers_exited.add(ticker_name)
                print(f"  {exit_action} {ticker_name}: {exit_price:,.0f}원 × {int(units)}주 = {amount:,.0f}원")
            except Exception as e:
                print(f"  [ERROR] {exit_action} 기록 실패 {ticker_name}: {e}")

    # ── BUY 처리 (Full Cash Sweep — 잔여현금 × 0.998) ───────────────────────────
    current_held = (set(open_positions.keys()) - tickers_exited)
    for sig in buy_candidates:
        ticker_name = sig['ticker']

        # 이미 보유 중이거나 오늘 EXIT한 종목 스킵
        if ticker_name in current_held or ticker_name in tickers_exited:
            continue
        # RS top-N 밖이면 BUY 안 함 (Switching 로직과 대칭)
        if ticker_name not in top_n_tickers:
            continue
        # 최대 포지션 수 체크
        if len(current_held) >= MAX_POSITIONS:
            break

        if ticker_name not in today_ohlcv:
            continue

        row        = today_ohlcv[ticker_name]
        open_price = float(row['open'])
        signal_close = float(sig.get('close', 0))
        hard_stop_pct = float(sig.get('hard_stop_loss_pct') or 0)

        # Full Cash Sweep: 잔여현금 × 0.998, 정수 주문만 허용
        invest = cash * 0.998
        if invest <= 0 or open_price <= 0:
            continue
        units  = int(invest / open_price)          # 소수점 버림 — 1주 단위 주문
        if units == 0:                              # 잔여현금으로 1주도 못 살 경우 스킵
            print(f"  [SKIP] {ticker_name}: 잔여현금 {cash:,.0f}원 < 1주({open_price:,.0f}원) — 매수 불가")
            continue
        amount = units * open_price                # 실제 체결금액 (invest 아님)

        try:
            _upsert_trade(sb, {
                "signal_date":   YESTERDAY_STR,
                "execute_date":  TODAY_STR,
                "ticker":        ticker_name,
                "action":        "BUY",
                "execute_price": open_price,
                "signal_close":  signal_close,
                "units":         float(units),
                "amount":        round(amount, 2),
                "hard_stop_pct": round(hard_stop_pct, 6),
            })
            cash -= amount
            current_held.add(ticker_name)
            print(f"  BUY  {ticker_name}: {open_price:,.0f}원 × {units}주 = {amount:,.0f}원  [stop={hard_stop_pct:.4f}]")
            break  # Full Cash Sweep — 1회 매수 후 종료 (몰빵 설계)
        except Exception as e:
            print(f"  [ERROR] BUY 기록 실패 {ticker_name}: {e}")


# ── TASK 3: 포트폴리오 가치 업데이트 ─────────────────────────────────────────
def task3_update_portfolio(all_today_signals: dict):
    print(f"\n[TASK 3] 포트폴리오 가치 업데이트 — date={TODAY_STR}")

    open_positions = _get_open_positions()   # {ticker_name: {units, entry_price, hard_stop_pct}}
    cash           = _calc_cash()

    # 보유 종목 평가액 (오늘 종가)
    positions_value = 0.0
    for ticker_name, pos in open_positions.items():
        latest = all_today_signals.get(ticker_name)
        if latest is not None:
            close_price = float(latest.get('close', 0))
            positions_value += pos['units'] * close_price

    total_value = cash + positions_value

    try:
        sb.table('live_portfolio_history').upsert({
            "date":             TODAY_STR,
            "total_value":      round(total_value, 2),
            "cash":             round(cash, 2),
            "positions_value":  round(positions_value, 2),
        }, on_conflict='date').execute()
        ret_pct = (total_value / INITIAL_CAPITAL - 1) * 100
        print(f"  현금={cash:,.0f}  보유={positions_value:,.0f}  총={total_value:,.0f}  수익률={ret_pct:+.2f}%")
    except Exception as e:
        print(f"  [ERROR] 포트폴리오 업데이트 실패: {e}")


# ── 헬퍼: live_trades upsert (hard_stop_pct 컬럼 없으면 fallback) ──────────────
_hard_stop_col_exists = None   # 캐시: None=미확인, True/False

def _upsert_trade(sb_client, record: dict):
    """live_trades upsert. hard_stop_pct 컬럼 미존재 시 자동 fallback."""
    global _hard_stop_col_exists
    if _hard_stop_col_exists is False:
        record = {k: v for k, v in record.items() if k != 'hard_stop_pct'}
    try:
        sb_client.table('live_trades').upsert(record, on_conflict='signal_date,ticker,action').execute()
        _hard_stop_col_exists = True
    except Exception as e:
        if '42703' in str(e) or 'hard_stop_pct does not exist' in str(e):
            print(f"  [WARN] hard_stop_pct 컬럼 없음 — fallback (컬럼 추가 필요)")
            _hard_stop_col_exists = False
            fallback = {k: v for k, v in record.items() if k != 'hard_stop_pct'}
            sb_client.table('live_trades').upsert(fallback, on_conflict='signal_date,ticker,action').execute()
        else:
            raise


# ── 헬퍼: 현재 오픈 포지션 ────────────────────────────────────────────────────
def _get_open_positions() -> dict:
    """live_trades에서 BUY 후 EXIT 안 된 종목 반환 {ticker: {units, entry_price, hard_stop_pct}}"""
    try:
        cols = 'ticker,action,units,execute_price,hard_stop_pct' if _hard_stop_col_exists is not False else 'ticker,action,units,execute_price'
        try:
            res = sb.table('live_trades').select(cols).execute()
        except Exception:
            res = sb.table('live_trades').select('ticker,action,units,execute_price').execute()
        pos = {}
        for r in res.data:
            if r['action'] == 'BUY':
                pos[r['ticker']] = {
                    'units':         float(r.get('units') or 0),
                    'entry_price':   float(r.get('execute_price') or 0),
                    'hard_stop_pct': float(r.get('hard_stop_pct') or 0),
                }
            elif r['action'] in ('EXIT', 'EXIT_HARDSTOP', 'EXIT_SWITCH') and r['ticker'] in pos:
                del pos[r['ticker']]
        return pos
    except Exception:
        return {}


def _calc_cash() -> float:
    """live_trades 기준 현금 잔액 계산"""
    try:
        res = sb.table('live_trades').select('action,amount').execute()
        cash = INITIAL_CAPITAL
        for r in res.data:
            if r['action'] == 'BUY':
                cash -= float(r['amount'])
            elif r['action'] in ('EXIT', 'EXIT_HARDSTOP', 'EXIT_SWITCH'):
                cash += float(r['amount'])
        return max(cash, 0.0)
    except Exception:
        return INITIAL_CAPITAL


# ── 메인 ──────────────────────────────────────────────────────────────────────
def task0_verify_tickers():
    """[TASK 0] 티커 무결성 검증 — 이름 불일치·데이터 없음 즉시 경고"""
    print(f"\n[TASK 0] 티커 무결성 검증 — {len(TARGET_ETFS)}종목")
    issues = verify_tickers(TARGET_ETFS)
    if not issues:
        print("  모든 티커 정상 ✅")
    else:
        print(f"  ⚠️  경고 {len(issues)}건 발견 — 즉시 확인 필요:")
        for msg in issues:
            print(f"    {msg}")
    return issues


def main():
    print("=" * 60)
    print(f" KODEX IRP 실전 신호/매매 자동 기록 — KST {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    task0_verify_tickers()
    all_today_signals = task1_save_signals()
    task2_record_executions()
    task3_update_portfolio(all_today_signals)

    print("\n[완료]")


if __name__ == "__main__":
    main()
