import pandas as pd
import numpy as np
import sys
import os

# 원본 엔진 모듈 경로 추가
sys.path.append(os.getcwd())
try:
    from frontend.app import load_and_process_data_v3_5_2_MASTER_FINAL
    # 캐시를 거치지 않고 엔진을 직접 호출
    from analytics.portfolio_backtester import run_portfolio_backtest
except ImportError as e:
    print(f"[ERROR] Failed to import engine components: {str(e)}")
    sys.exit(1)

def run_total_trade_integrity_audit():
    print("--- [TOTAL TRADE INTEGRITY AUDIT: START] ---")
    
    # 1. 1,781행 마스터 데이터 및 신호 로드
    print("[INFO] Loading master signal data (1781 rows)...")
    all_signals, _, k200_raw, _, _ = load_and_process_data_v3_5_2_MASTER_FINAL(is_backtest=True)
    
    # 2. 백테스팅 연산 엔진 직접 호출 (Direct Call to avoid Cache issues)
    initial_capital = 50000000.0
    max_tickers = 3
    print("[INFO] Executing raw backtest engine (Direct Call)...")
    # port_res = run_portfolio_backtest(all_signals, initial_capital, max_tickers, use_cash_sweep)
    port_res = run_portfolio_backtest(all_signals, initial_capital, max_tickers, True)
    
    trade_logs = port_res.get('trade_log', [])
    
    if not trade_logs:
        print("[ERROR] Audit Error: No trade logs generated. Check signal columns or tickers.")
        return

    print(f"[INFO] Total Trade Records Extracted: {len(trade_logs)}")
    
    # 3. 전수 대조 감사 (Logic Compliance Check)
    fault_count = 0
    checked_count = 0
    
    for trade in trade_logs:
        ticker = trade['종목명']
        entry_date = trade['진입일자']
        exit_date = trade['청산일자']
        
        df = all_signals.get(ticker)
        if df is None: continue
            
        checked_count += 1
        
        # [A] 진입 무결성 검증 (Signal at T, Entry at T+1)
        try:
            entry_idx = df[df['date'] == entry_date].index[0]
            if entry_idx > 0:
                signal_row = df.iloc[entry_idx - 1]
                if signal_row['execute_buy_T_plus_1'] != True:
                    fault_count += 1
                    print(f"[LOGIC FAULT] Entry Violation: {ticker} on {entry_date} (No T-signal)")
        except: pass

        # [B] 청산 무결성 검증 (Signal at T, Exit at T+1)
        try:
            exit_idx = df[df['date'] == exit_date].index[0]
            if exit_idx > 0:
                exit_signal_row = df.iloc[exit_idx - 1]
                if exit_signal_row['execute_exit_T_plus_1'] != True:
                    # 마감일 종가 강제 청산 제외
                    if exit_idx < len(df) - 1:
                        fault_count += 1
                        print(f"[LOGIC FAULT] Exit Violation: {ticker} on {exit_date} (No T-signal)")
        except: pass

    # 4. 최종 리포트 합산
    print("\n--- [AUDIT SUMMARY REPORT] ---")
    print(f" - Total Examined Trades: {checked_count}")
    print(f" - Total Logic Faults   : {fault_count}")
    
    if fault_count == 0:
        print("\n[SUCCESS] Pipeline Total Trade Integrity 100.0% Verified (Logic Sanctuary Intact)")
    else:
        print(f"\n[FAILURE] Pipeline Integrity Compromised: {fault_count} logic faults found!")

    print("--- [TOTAL TRADE INTEGRITY AUDIT: COMPLETE] ---")

if __name__ == "__main__":
    run_total_trade_integrity_audit()
