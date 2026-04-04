import os
import sys
import io
import pandas as pd

# UTF-8 출력 강제 (Windows 대응)
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

# Add current directory to sys.path
sys.path.append(os.getcwd())

from frontend.app import load_and_process_data_v3_1_2
from analytics.portfolio_backtester import run_portfolio_backtest

def final_revert_check():
    # 데이터 로드 (현재 V3.5.0 원복된 상태)
    all_signals, _, _ = load_and_process_data_v3_1_2()
    
    # 백테스트 실행 (기본 5종목 분산)
    res = run_portfolio_backtest(all_signals, 50000000.0, 5, True)
    
    print(f"✅ 원복 완료 (V3.5.0 Baseline)")
    print(f"📊 누적 수익률: {res.get('cumulative_return'):.2f}% (기대치: 190.26%)")
    print(f"📉 MDD: {res.get('mdd'):.2f}%")

if __name__ == "__main__":
    final_revert_check()
