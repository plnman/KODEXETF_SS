import pandas as pd
import numpy as np
import sys
import os
import FinanceDataReader as fdr

# 원본 엔진 모듈 경로 추가
sys.path.append(os.getcwd())
try:
    from engine.strategy import build_signals_and_targets, get_market_regime
    from analytics.portfolio_backtester import run_portfolio_backtest
    from engine.indicators import calculate_adx
    from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity
except ImportError as e:
    print(f"[ERROR] Failed to import engine components: {str(e)}")
    sys.exit(1)

# [V3.5.2] 22종목 유니버스
TARGET_ETFS = {
    "069500": "KODEX 200", "226490": "KODEX 코스닥150", "379800": "KODEX 미국S&P500TR",
    "367380": "KODEX 미국나스닥100TR", "314250": "KODEX 미국FANG플러스(H)", "091160": "KODEX 반도체",
    "305720": "KODEX 2차전지산업", "465610": "KODEX 미국반도체MV", "453850": "KODEX 인도Nifty50",
    "244580": "KODEX 바이오", "461580": "KODEX 미국배당프리미엄액티브",
    "315930": "KODEX Top5PlusTR", "091170": "KODEX 은행", "091180": "KODEX 자동차",
    "117700": "KODEX 건설", "091220": "KODEX 금융", "102970": "KODEX 기계장비", "117680": "KODEX 철강",
    "315270": "KODEX 미국산업재(합성)", "251350": "KODEX 선진국MSCI World", "475380": "KODEX 글로벌AI인프라"
}

def clean_df(df):
    if df is None or df.empty: return None
    df.columns = [str(c).capitalize() for c in df.columns]
    if 'Date' not in df.columns:
        df = df.reset_index().rename(columns={'index': 'Date'})
    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
    return df.sort_values('Date')

def prepare_indicators(df):
    df_in = df.copy()
    df_in.columns = [str(c).lower() for c in df_in.columns]
    df_in = calculate_adx(df_in)
    df_cap = df.copy()
    df_in['mfi'] = calculate_mfi(df_cap)
    df_in['intraday_intensity'] = calculate_intraday_intensity(df_cap).rolling(window=21).sum()
    return df_in

def run_standalone_audit():
    print("--- [FINAL TRADES AUDIT: START] ---")
    warmup_start = "2018-01-01"
    audit_start = "2019-01-02"
    end_date = "2026-04-03"
    
    k200_raw = clean_df(fdr.DataReader("069500", start=warmup_start, end=end_date))
    k200 = prepare_indicators(k200_raw).set_index('date')
    k200_signals = build_signals_and_targets(k200.reset_index(), "KODEX 200", turbo_discount=0.5)
    regime_series = get_market_regime(k200_signals, use_global_mfi=True)
    regime_series.index = k200_signals['date'].values

    all_signals = {}
    for tk, name in TARGET_ETFS.items():
        df_raw = clean_df(fdr.DataReader(tk, start=warmup_start, end=end_date))
        if df_raw is None: continue
        df_prepared = prepare_indicators(df_raw)
        df_sync = df_prepared.set_index('date').reindex(k200.index).reset_index().ffill().fillna(0)
        reg_aligned = regime_series.reindex(df_sync.set_index('date').index).fillna(True)
        signals = build_signals_and_targets(df_sync, ticker_name=name, is_bull_market=reg_aligned, turbo_discount=0.5)
        all_signals[name] = signals[signals['date'] >= audit_start]

    port_res = run_portfolio_backtest(all_signals, 50000000.0, 3, True)
    
    # [V3.5.2 FIX] Corrected key name from 'trade_log' to 'trades_df'
    trades_df = port_res.get('trades_df', pd.DataFrame())
    
    if trades_df.empty:
        print("[ERROR] Still 0 trades. Reviewing all_signals columns...")
        return

    trade_records = trades_df.to_dict('records')
    print(f"[INFO] Analyzed {len(trade_records)} trade records.")
    
    fault_count = 0
    for trade in trade_records:
        tk, entry, exit = trade['종목명'], trade['진입일자'], trade['청산일자']
        df = all_signals.get(tk)
        if df is None: continue
        # [A] Entry Integrity (T-1 signal check)
        try:
            # Sliced DF에서 현재 진입일의 '위치'를 찾음
            pos_list = np.where(df['date'] == entry)[0]
            if len(pos_list) > 0:
                pos = pos_list[0]
                if pos > 0:
                    sig_t = df.iloc[pos - 1]
                    if sig_t['execute_buy_T_plus_1'] != True:
                        print(f"[FAULT] ENTRY VIOLATION: {tk} on {entry}")
                        fault_count += 1
        except Exception as e:
            print(f"[DEBUG] Entry Check Error: {e}")
        
        # [B] Exit Integrity (T-1 signal check)
        try:
            pos_list = np.where(df['date'] == exit)[0]
            if len(pos_list) > 0:
                pos = pos_list[0]
                if pos > 0:
                    sig_x = df.iloc[pos - 1]
                    if sig_x['execute_exit_T_plus_1'] != True:
                        if pos < len(df) - 1:
                            print(f"[FAULT] EXIT VIOLATION: {tk} on {exit}")
                            fault_count += 1
        except Exception as e:
            print(f"[DEBUG] Exit Check Error: {e}")

    print(f"\n[FINAL SUMMARY]\n - Examined: {len(trade_records)}\n - Deviations: {fault_count}")
    if fault_count == 0: print("[SUCCESS] 100% LOGIC COMPLIANCE.")
    else: print("[FAILURE] DISCREPANCIES DETECTED.")
    print("--- [AUDIT COMPLETE] ---")

if __name__ == "__main__":
    run_standalone_audit()
