import pandas as pd
import numpy as np

def run_vectorized_backtest(enhanced_df: pd.DataFrame, initial_capital: float = 50000000.0) -> dict:
    """
    [고속 벡터라이징 백테스터]
    strategy.py에서 도출된 `execute_buy_T_plus_1` 시그널과 
    `hard_stop_loss_pct`를 기반으로 백테스팅을 수행하고 성과 지표를 산출합니다.
    """
    if enhanced_df.empty or 'execute_buy_T_plus_1' not in enhanced_df.columns:
        return {"error": "Insufficient data or missing signals"}

    trades = []
    capital = initial_capital
    position = 0  # 0: 무포지션, 1: 매수 상태
    entry_price = 0.0
    
    # 시간 순서대로 정렬 확인
    df = enhanced_df.sort_values('date').reset_index(drop=True)
    
    for i, row in df.iterrows():
        # 1. T+1 시가 매수 진입 룰 적용
        if position == 0 and row['execute_buy_T_plus_1'] == True:
            position = 1
            entry_price = row['open']
        
        # 2. 매수한 종목 청산 룰 적용
        elif position == 1:
            hard_stop_price = entry_price * (1 - row['hard_stop_loss_pct'])
            target_profit_price = entry_price * 1.10 # 10% Trailing 익절선 (예시)
            
            # 장중 폭락 시 손절 (Hard Stop)
            if row['low'] <= hard_stop_price:
                exit_price = hard_stop_price
                position = 0
            # 10% 급등 시 익절
            elif row['high'] >= target_profit_price:
                exit_price = target_profit_price
                position = 0
            # 기본 청산: 데이트레이딩 오버나이트 방지 룰에 따라 "당일 종가 청산"
            else:
                exit_price = row['close']
                position = 0
                
            if position == 0:
                profit_pct = (exit_price - entry_price) / entry_price
                trades.append(profit_pct)
                capital *= (1 + profit_pct)
                
    # 3. 성과 지표(Performance Metrics) 연산
    total_trades = len(trades)
    win_trades = len([t for t in trades if t > 0])
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0.0
    
    # CAGR 연산용 (전체 기간 연수 산출)
    if 'date' in df.columns and not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        days = (df['date'].max() - df['date'].min()).days
        years = max(days / 365.25, 0.5)
    else:
        years = 1
        
    cagr = ((capital / initial_capital) ** (1 / years) - 1) * 100
    
    return {
        "initial_capital": initial_capital,
        "final_capital": round(capital, 0),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "cagr": round(cagr, 2),
        "trades_list": trades
    }
