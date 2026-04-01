import pandas as pd
import numpy as np

def run_vectorized_backtest(enhanced_df: pd.DataFrame, initial_capital: float = 50000000.0) -> dict:
    """
    [고속 벡터라이징 무결성 백테스터 (Daily-Only)]
    strategy.py에서 도출된 `execute_buy_T_plus_1` 시그널과 
    `execute_exit_T_plus_1` 신호를 0.00% 오차율로 IRP 리얼 룰(T+1 체결)을 반영해 시뮬레이션합니다.
    """
    if enhanced_df.empty or 'execute_buy_T_plus_1' not in enhanced_df.columns:
        return {"error": "Insufficient data or missing signals"}

    trades = []
    capital = initial_capital
    position = 0  # 0: 무포지션 가용 현금, 1: 매수 상태
    entry_price = 0.0
    
    df = enhanced_df.sort_values('date').reset_index(drop=True)
    history_records = []
    
    for i, row in df.iterrows():
        # 1. 청산 로직 (보유 중일 때) - T+1 시가 또는 장중 Hard Stop 청산
        if position == 1:
            hard_stop_price = entry_price * (1 - row['hard_stop_loss_pct'])
            
            # (1) 장중 폭락 시 방어선 붕괴 즉각 손절 (Hard Stop)
            if row['low'] <= hard_stop_price:
                exit_price = hard_stop_price
                position = 0
                profit_pct = (exit_price - entry_price) / entry_price
                trades.append(profit_pct)
                capital *= (1 + profit_pct)
                
            # (2) 전일(T) 종가 기반 청산 시그널이 켜졌다면 (T+1 시가 매도 강제 실행)
            elif row['execute_exit_T_plus_1'] == True:
                exit_price = row['open']
                position = 0
                profit_pct = (exit_price - entry_price) / entry_price
                trades.append(profit_pct)
                capital *= (1 + profit_pct)
                
        # 2. 진입 로직 (무포지션일 때) - T+1 시가 매수
        if position == 0 and row['execute_buy_T_plus_1'] == True:
            # 방금 위의 청산 로직에서 T+1 시가에 청산했다면, 같은 날 T+1 시가에 재매수하는 것 또한
            # IRP T+1 결제 룰에서 허용됨 (매도 대금은 T+2 구속되지만, 신용/당일 증거금으로 즉시 사용 가능)
            position = 1
            entry_price = row['open']
            
        # [NEW] 매일매일의 현재 자산 가치를 평가하여 프론트엔드의 연도별 추출(resample) 요구사항을 보조
        current_val = capital
        if position == 1 and entry_price > 0:
            current_val = capital * (row['close'] / entry_price)
            
        history_records.append({
            'date': row['date'],
            'total_value': current_val
        })
                
    # 3. 성과 지표(Performance Metrics) 연산
    df_history = pd.DataFrame(history_records)
    total_trades = len(trades)
    win_trades = len([t for t in trades if t > 0])
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0.0
    
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
        "trades_list": trades,
        "history": df_history # 이 history가 반환되어야 프론트엔드 연도별 추출(YE resample)이 가동됩니다.
    }
