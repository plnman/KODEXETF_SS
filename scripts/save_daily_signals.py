"""
scripts/save_daily_signals.py
==============================
매일 16:10 KST (07:10 UTC) GitHub Actions에 의해 자동 실행.

[TASK 1] 오늘 신호 기록
  - 전체 23개 ETF 실전 신호 계산 → Supabase daily_signals 저장

[TASK 2] 전날 신호 체결 기록 (V3.6.1)
  - 전날 buy_signal=True / exit_signal=True 종목 조회
  - 오늘 시가(open)로 체결가 확정 → live_trades 저장

[TASK 3] 포트폴리오 가치 업데이트 (V3.6.1)
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
)
from engine.strategy import build_signals_and_targets

# ── 설정 ──────────────────────────────────────────────────────────────────────
LOOKBACK_DAYS    = 500
INITIAL_CAPITAL  = 50_000_000.0
MAX_POSITIONS    = 5
ALLOC_PER_POS    = INITIAL_CAPITAL / MAX_POSITIONS   # 1종목당 10,000,000원
KST              = pytz.timezone('Asia/Seoul')
now_kst          = datetime.now(KST)
TODAY_STR        = now_kst.strftime("%Y-%m-%d")
YESTERDAY_STR    = (now_kst - timedelta(days=1)).strftime("%Y-%m-%d")

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


# ── TASK 1: 오늘 신호 기록 ────────────────────────────────────────────────────
def task1_save_signals():
    print(f"\n[TASK 1] 신호 기록 — signal_date={TODAY_STR}")
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
            sig     = build_signals_and_targets(df.copy(), ticker_name=ticker_name, is_bull_market=False)
            latest  = sig.iloc[-1]
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
            }
            sb.table('daily_signals').upsert(record, on_conflict='signal_date,ticker').execute()
            mark = "BUY" if record['buy_signal'] else ("EXIT" if record['exit_signal'] else "---")
            print(f"OK [{mark}]")
            success += 1
        except Exception as e:
            print(f"ERROR: {e}")
            fail += 1

    print(f"  → 성공={success} 실패={fail}")
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

    yesterday_signals = {r['ticker']: r for r in res.data}

    # 현재 보유 포지션 조회 (EXIT 여부 확인용)
    open_positions = _get_open_positions()

    for ticker_name, sig in yesterday_signals.items():
        fdr_code = FDR_CODE.get(ticker_name)
        if not fdr_code:
            continue

        # 오늘 시가 조회 (load_ticker의 len<30 필터 우회를 위해 60일치 조회 후 오늘 행 필터)
        recent_start = (now_kst - timedelta(days=60)).strftime("%Y-%m-%d")
        df_today = load_ticker(fdr_code, start=recent_start)
        if df_today is None or df_today.empty:
            continue
        today_row = df_today[df_today['date'].dt.strftime('%Y-%m-%d') == TODAY_STR]
        if today_row.empty:
            continue
        open_price  = float(today_row.iloc[0]['open'])
        signal_close = float(sig.get('close', 0))

        # BUY 체결
        if sig.get('buy_signal') and ticker_name not in open_positions and len(open_positions) < MAX_POSITIONS:
            allocation = ALLOC_PER_POS
            units      = allocation / open_price if open_price > 0 else 0
            try:
                sb.table('live_trades').upsert({
                    "signal_date":   YESTERDAY_STR,
                    "execute_date":  TODAY_STR,
                    "ticker":        ticker_name,
                    "action":        "BUY",
                    "execute_price": open_price,
                    "signal_close":  signal_close,
                    "units":         round(units, 6),
                    "amount":        round(units * open_price, 2),
                }, on_conflict='signal_date,ticker,action').execute()
                open_positions[ticker_name] = units
                print(f"  BUY  {ticker_name}: {open_price:,.0f}원 × {units:.2f}주 = {units*open_price:,.0f}원")
            except Exception as e:
                print(f"  [ERROR] BUY 기록 실패 {ticker_name}: {e}")

        # EXIT 체결
        elif sig.get('exit_signal') and ticker_name in open_positions:
            units = open_positions[ticker_name]
            try:
                sb.table('live_trades').upsert({
                    "signal_date":   YESTERDAY_STR,
                    "execute_date":  TODAY_STR,
                    "ticker":        ticker_name,
                    "action":        "EXIT",
                    "execute_price": open_price,
                    "signal_close":  signal_close,
                    "units":         round(units, 6),
                    "amount":        round(units * open_price, 2),
                }, on_conflict='signal_date,ticker,action').execute()
                del open_positions[ticker_name]
                print(f"  EXIT {ticker_name}: {open_price:,.0f}원 × {units:.2f}주 = {units*open_price:,.0f}원")
            except Exception as e:
                print(f"  [ERROR] EXIT 기록 실패 {ticker_name}: {e}")


# ── TASK 3: 포트폴리오 가치 업데이트 ─────────────────────────────────────────
def task3_update_portfolio(all_today_signals: dict):
    print(f"\n[TASK 3] 포트폴리오 가치 업데이트 — date={TODAY_STR}")

    open_positions = _get_open_positions()   # {ticker_name: units}
    cash           = _calc_cash()

    # 보유 종목 평가액 (오늘 종가)
    positions_value = 0.0
    for ticker_name, units in open_positions.items():
        latest = all_today_signals.get(ticker_name)
        if latest is not None:
            close_price = float(latest.get('close', 0))
            positions_value += units * close_price

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


# ── 헬퍼: 현재 오픈 포지션 ────────────────────────────────────────────────────
def _get_open_positions() -> dict:
    """live_trades에서 BUY 후 EXIT 안 된 종목 반환 {ticker: units}"""
    try:
        res = sb.table('live_trades').select('ticker,action,units').execute()
        pos = {}
        for r in res.data:
            if r['action'] == 'BUY':
                pos[r['ticker']] = float(r['units'])
            elif r['action'] == 'EXIT' and r['ticker'] in pos:
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
            elif r['action'] == 'EXIT':
                cash += float(r['amount'])
        return max(cash, 0.0)
    except Exception:
        return INITIAL_CAPITAL


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f" KODEX IRP 실전 신호/매매 자동 기록 — KST {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_today_signals = task1_save_signals()
    task2_record_executions()
    task3_update_portfolio(all_today_signals)

    print("\n[완료]")


if __name__ == "__main__":
    main()
