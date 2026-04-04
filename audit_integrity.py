import pandas as pd
import numpy as np
import sys
import os
import streamlit as st

# 원본 엔진 모듈 경로 추가
sys.path.append(os.getcwd())
from frontend.app import load_and_process_data_v3_5_2_FINAL

def run_hard_audit():
    print(f"--- [PIPELINE HARD AUDIT: START] ---")
    
    # 1,781행 마스터 데이터 로드 (KRX+Naver Dual Baseline)
    all_signals, _, k200_raw, _, integrity = load_and_process_data_v3_5_2_FINAL(is_backtest=True)
    
    total_dates = len(k200_raw)
    print(f"Total Master Dates: {total_dates} (Baseline: 1781)")
    print(f"Integrity Score: {integrity.get('score')}%")
    
    audit_results = []
    for name, df in all_signals.items():
        zero_prices = (df['close'] == 0).sum()
        # 가격이 0원일 때 매수 신호가 발생했는지 (Ghost Buy Detection)
        ghost_buys = ((df['close'] == 0) & (df['buy_signal_T'] == True)).sum()
        
        audit_results.append({
            "Ticker": name,
            "ZeroDays": zero_prices,
            "GhostBuys": ghost_buys,
            "ValidDays": len(df) - zero_prices
        })
    
    df_audit = pd.DataFrame(audit_results)
    print("\n[Detail Signal Integrity Report]")
    print(df_audit.to_string(index=False))
    
    total_ghosts = df_audit['GhostBuys'].sum()
    if total_ghosts == 0:
        print(f"\n[SUCCESS] Pipeline Integrity Verified: Ghost Buy 0 (Sanctuary Protected)")
    else:
        print(f"\n[CRITICAL] Pipeline Pollution Detected: {total_ghosts} Ghost Buys Found!")

    print(f"--- [PIPELINE HARD AUDIT: COMPLETE] ---")

if __name__ == "__main__":
    run_hard_audit()
