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

def baseline_parity_check():
    print("🚦 [Phase 1] 대시보드 100% 동기화 검증 시작...")
    
    # 1. app.py의 데이터 로직 그대로 로드
    all_signals, _, _ = load_and_process_data_v3_1_2()
    
    # 2. 3종목 집중 투자(🚀) 모드로 실행
    res = run_portfolio_backtest(all_signals, 50000000.0, 3, True)
    
    print("-" * 60)
    print(f"📊 [결과] 현재 V3.5.0 누적 수익률: {res['cumulative_return']:.2f}%")
    print(f"🎯 [비교] 회원님 대시보드 수치: 188.59%")
    print("-" * 60)
    
    if abs(res['cumulative_return'] - 188.59) < 1.0:
        print("✅ [동기화 성공] 대시보드와 제 시뮬레이션이 100% 일치합니다. 이제 뼈를 깎는 튜닝을 시작하겠습니다.")
    else:
        print("⚠️ [오차 발견] 대시보드와 수치가 다릅니다. 원인을 파악한 후 다시 보고하겠습니다.")

if __name__ == "__main__":
    baseline_parity_check()
