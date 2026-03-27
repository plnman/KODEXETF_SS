import numpy as np

def run_monte_carlo_crisis_test(trades_list: list, iterations: int = 5000, max_drawdown_limit: float = 0.3) -> dict:
    """
    [Crisis Stress Test / Monte Carlo 시뮬레이터]
    백테스터가 생산한 트레이드 손익(% 배열)을 리샘플링하여 미래 1년의 가상 시나리오를 수천 번 생성.
    기존 마스터 플랜(사용자 요구사항)에 명시된 "2008년 무한 하락장", "2020년 코로나 빔" 같은 
    스트레스 구간을 랜덤하게 강제 주입하여 파산 확률(Probability of Ruin)을 가혹하게 검증합니다.
    
    - max_drawdown_limit: 0.3 이면, 30% 손실 발생 시 파산(Ruin)으로 규정
    """
    if not trades_list or len(trades_list) < 5:
        return {"p_ruin": 0.0, "expected_mdd": 0.0, "status": "Not enough data"}
        
    n_trades = min(len(trades_list), 252) # 향후 1년가량의 트레이드 횟수 가정
    bankruptcy_count = 0
    mdd_list = []
    
    # 금융위기/가속 하락장(Stress) 모사를 위해, 오직 최악의 5% Trade들만 따로 빼놓습니다.
    sorted_trades = sorted(trades_list)
    worst_5_percent = sorted_trades[:max(1, int(len(trades_list) * 0.05))]
    
    for _ in range(iterations):
        # 1. 붓스트랩핑 복원 추출 (통상적인 시장)
        simulated_trades = np.random.choice(trades_list, size=n_trades, replace=True)
        
        # 2. Crisis Event 주입: 매 시나리오의 2% 확률로 연쇄적인 대폭락 장세 강제 조작
        is_crisis = np.random.random() < 0.02
        if is_crisis:
            # 2주(약 10거래일) 연속으로 기존 기록 중 "최악의 손실"만 뽑아서 덮어씌움
            crisis_duration = 10
            start_idx = np.random.randint(0, n_trades - crisis_duration)
            simulated_trades[start_idx:start_idx+crisis_duration] = np.random.choice(worst_5_percent, size=crisis_duration)
            
        # 3. 누적 수익률(Equity Curve) 추적을 통한 MDD 산출 계기
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        bankrupt = False
        
        for trade_pct in simulated_trades:
            equity *= (1 + trade_pct)
            
            if equity > peak:
                peak = equity
                
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd
            
            # 파산 트리거 확인
            if max_dd >= max_drawdown_limit:
                bankrupt = True
                break # 이미 파산했으므로 뒤는 시뮬레이션 불필요
                
        mdd_list.append(max_dd)
        if bankrupt:
            bankruptcy_count += 1
            
    # 최종 결과 도출
    p_ruin = (bankruptcy_count / iterations) * 100
    expected_mdd = np.mean(mdd_list) * 100
    
    return {
        "p_ruin": round(p_ruin, 2),
        "expected_mdd": round(expected_mdd, 2),
        "iterations": iterations,
        "stress_test_applied": True
    }
