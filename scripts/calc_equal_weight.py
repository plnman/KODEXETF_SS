"""
Equal Weight vs Full Cash Sweep 비교 재계산
app.py와 동일한 데이터 로딩 로직 사용 (len<30 필터 없음)
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import FinanceDataReader as fdr
from datetime import datetime

from config.etf_universe import ETF_UNIVERSE, TARGET_ETFS
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity
from engine.strategy import build_signals_and_targets, get_market_regime

START_DATE = "2019-01-01"
END_DATE   = "2026-04-04"
INITIAL    = 50_000_000.0

def clean_df(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    if 'date' not in df.columns:
        df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    return df.sort_values('date')

def get_ticker_data(code, start, end):
    """app.py get_single_ticker_data와 동일 — empty 아니면 반환"""
    clean_code = code.replace(".KS","").replace(".KQ","")
    try:
        df = fdr.DataReader(clean_code, start=start, end=end)
        if df.empty:
            return None
        df = clean_df(df)
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        return df
    except Exception as e:
        print(f"  [WARN] {clean_code} 로드 실패: {e}")
        return None

def run_backtest(all_signals: dict, initial_capital: float, max_tickers: int, equal_weight: bool) -> dict:
    daily_data = {t: df.set_index('date') for t, df in all_signals.items()}
    unique_dates = sorted(set(d for df in all_signals.values() for d in df['date'].tolist()))

    capital = initial_capital
    positions = {}
    current_target_tickers = []
    trade_count = 0
    portfolio_history = []
    alloc_per_pos = initial_capital / max_tickers  # equal weight 용

    for current_date in unique_dates:
        today_rows = {t: daily_data[t].loc[current_date]
                      for t in daily_data if current_date in daily_data[t].index}

        # [1] 청산
        tickers_to_remove = []
        for ticker, pos in positions.items():
            if ticker not in today_rows:
                continue
            row = today_rows[ticker]
            hard_stop_price = pos['entry_price'] * (1 - pos['hard_stop_pct'])
            exit_price = None
            if row['low'] <= hard_stop_price:
                exit_price = hard_stop_price
            elif ticker not in current_target_tickers:
                exit_price = row['open']
            elif row['execute_exit_T_plus_1'] == True:
                exit_price = row['open']
            if exit_price is not None:
                capital += pos['qty'] * exit_price
                tickers_to_remove.append(ticker)
        for t in tickers_to_remove:
            del positions[t]

        # [2] 진입
        for ticker in current_target_tickers:
            if ticker in positions or ticker not in today_rows:
                continue
            row = today_rows[ticker]
            if row['execute_buy_T_plus_1'] != True:
                continue
            if equal_weight:
                invest = alloc_per_pos
            else:
                invest = capital * 0.998  # Full Cash Sweep
            if capital < invest or invest <= 0:
                continue
            qty = int(invest // row['open'])
            if qty <= 0:
                continue
            capital -= qty * row['open']
            positions[ticker] = {
                'qty': qty,
                'entry_price': row['open'],
                'hard_stop_pct': row['hard_stop_loss_pct'],
            }
            trade_count += 1

        # [3] RS 스크리닝
        rs_scores = {}
        for t, row in today_rows.items():
            col = 'composite_rs' if 'composite_rs' in row else 'rs_20'
            if col in row and not pd.isna(row[col]) and not np.isinf(row[col]):
                rs_scores[t] = row[col]
        sorted_tickers = sorted(rs_scores.items(), key=lambda x: x[1], reverse=True)
        current_target_tickers = [x[0] for x in sorted_tickers[:max_tickers]]

        # [4] 잔고 평가
        daily_value = capital + sum(
            pos['qty'] * today_rows[t]['close']
            for t, pos in positions.items() if t in today_rows
        )
        portfolio_history.append({'date': current_date, 'total_value': daily_value})

    df_hist = pd.DataFrame(portfolio_history)
    mdd = 0
    if not df_hist.empty:
        df_hist['peak'] = df_hist['total_value'].cummax()
        df_hist['dd'] = (df_hist['total_value'] - df_hist['peak']) / df_hist['peak']
        mdd = df_hist['dd'].min() * 100

    final_val = df_hist['total_value'].iloc[-1] if not df_hist.empty else initial_capital
    ret = (final_val / initial_capital - 1) * 100
    years = (pd.to_datetime(df_hist['date'].iloc[-1]) - pd.to_datetime(df_hist['date'].iloc[0])).days / 365.25 if not df_hist.empty else 1
    cagr = ((final_val / initial_capital) ** (1 / max(years, 0.5)) - 1) * 100
    return {"ret": round(ret,2), "cagr": round(cagr,2), "mdd": round(mdd,2), "trades": trade_count}


def main():
    print("=" * 65)
    print(" Equal Weight vs Full Cash Sweep 정밀 재계산")
    print(f" 데이터: {START_DATE} ~ {END_DATE}  |  초기자본: {INITIAL:,.0f}원")
    print("=" * 65)

    # K200 로드 (레짐 판독용)
    print("\n[1] K200 로드 및 레짐 계산...")
    k200 = fdr.DataReader("069500", start=START_DATE, end=END_DATE)
    k200 = clean_df(k200)
    k200 = k200[(k200['date'] >= "2019-01-02") & (k200['date'] <= "2026-04-03")]
    k200['mfi'] = calculate_mfi(k200)
    k200['intraday_intensity'] = calculate_intraday_intensity(k200)
    k200_sig = build_signals_and_targets(k200, "KODEX 200", turbo_discount=0.5)
    regime_series = get_market_regime(k200_sig, use_global_mfi=True)
    print(f"  K200: {len(k200)}행")

    # 전 종목 로드 (app.py와 동일 — empty 아니면 포함)
    print("\n[2] ETF 데이터 로드 (15종목)...")
    all_signals = {}
    for code, name in TARGET_ETFS.items():
        df = get_ticker_data(code, START_DATE, END_DATE)
        if df is None:
            print(f"  SKIP: {name} ({code})")
            continue
        df_sync = df.set_index('date').reindex(k200.set_index('date').index).reset_index().ffill().fillna(0)
        df_sync = df_sync.drop_duplicates(subset=['date'])
        regime_aligned = regime_series.reindex(df_sync.set_index('date').index).fillna(True)
        sig = build_signals_and_targets(df_sync, ticker_name=name, is_bull_market=regime_aligned, turbo_discount=0.4)
        all_signals[name] = sig
        print(f"  OK  : {name} ({len(sig)}행)")

    print(f"\n  → 총 {len(all_signals)}/{len(TARGET_ETFS)} 종목 로드 완료")

    # 재계산
    print("\n[3] 백테스팅 재계산...")
    print(f"\n{'종목':>4} | {'방식':<18} | {'수익률':>8} | {'CAGR':>7} | {'MDD':>8} | {'거래수':>6}")
    print("-" * 65)

    BASELINE = {3: 298.51, 5: 292.60, 10: 513.34}

    for n in [3, 5, 10]:
        r_fcs = run_backtest(all_signals, INITIAL, n, equal_weight=False)
        r_ew  = run_backtest(all_signals, INITIAL, n, equal_weight=True)
        print(f"  {n}종목 | Full Cash Sweep   | {r_fcs['ret']:>7.2f}% | {r_fcs['cagr']:>6.2f}% | {r_fcs['mdd']:>7.2f}% | {r_fcs['trades']:>5}건")
        print(f"  {n}종목 | Equal Weight      | {r_ew['ret']:>7.2f}% | {r_ew['cagr']:>6.2f}% | {r_ew['mdd']:>7.2f}% | {r_ew['trades']:>5}건")
        print(f"  {n}종목 | BASELINE (저장값) | {BASELINE[n]:>7.2f}% |        |          |")
        print("-" * 65)

    print("\n[완료]")

if __name__ == "__main__":
    main()
