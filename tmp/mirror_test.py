import os
import sys
import io
import pandas as pd
from datetime import datetime

# UTF-8 출력 강제 (Windows 대응)
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

# Add current directory to sys.path
sys.path.append(os.getcwd())

from frontend.app import load_and_process_data_v3_1_2
from analytics.portfolio_backtester import run_portfolio_backtest

def mirror_test():
    print("🚦 [진실의 거울] 대시보드와 100% 동일한 로직으로 전수 재검증 중...")
    
    # 1. 데이터 로드 (app.py의 load_and_process_data_v3_1_2와 동일하게)
    all_signals, _, _ = load_and_process_data_v3_1_2()
    
    # 2. 3종목 모드 (수익률 집중형) 백테스트
    res3 = run_portfolio_backtest(all_signals, 50000000.0, 3, True)
    
    # 3. 5종목 모드 (표준형) 백테스트
    res5 = run_portfolio_backtest(all_signals, 50000000.0, 5, True)
    
    # 4. 10종목 모드 (안정형) 백테스트
    res10 = run_portfolio_backtest(all_signals, 50000000.0, 10, True)

    print("-" * 60)
    print(f"🚀 [3종목] 누적 수익률: {res3['cumulative_return']:.2f}% (대시보드와 일치하는가?)")
    print(f"🛡️ [5종목] 누적 수익률: {res5['cumulative_return']:.2f}%")
    print(f"🏦 [10종목] 누적 수익률: {res10['cumulative_return']:.2f}%")
    print("-" * 60)
    
    # BASELINE_RET = 229.37 와의 오차 계산 (현 V3.5.0 기준)
    baseline = 229.37
    error3 = res3['cumulative_return'] - baseline
    print(f"⚠️ [3종목] 정밀 오차: {error3:+.2f}% (대시보드 -40.78%와 일치하는가?)")

if __name__ == "__main__":
    mirror_test()
