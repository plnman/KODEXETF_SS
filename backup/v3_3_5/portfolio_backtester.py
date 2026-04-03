import pandas as pd

def run_portfolio_backtest(all_signals_dict: dict, initial_capital: float = 50000000.0, max_tickers: int = 10, weight_per_ticker: float = 0.1) -> dict:
    daily_data = {}
    for ticker, df in all_signals_dict.items():
        daily_data[ticker] = df.set_index('date')

    unique_dates_set = set()
    for df in all_signals_dict.values():
        unique_dates_set.update(df['date'].tolist())
    unique_dates = sorted(list(unique_dates_set))
    
    capital = initial_capital
    positions = {} 
    
    portfolio_history = []
    trade_logs = []  # 개별 매매 상세 결산 로그
    current_target_tickers = []
    
    for t_idx, current_date in enumerate(unique_dates):
        dt_obj = pd.to_datetime(current_date)
        is_friday = (dt_obj.weekday() == 4)
        
        today_rows = {}
        for ticker, df in daily_data.items():
            if current_date in df.index:
                today_rows[ticker] = df.loc[current_date]
        
        # [1] 청산 처리
        tickers_to_remove = []
        for ticker, pos in positions.items():
            if ticker in today_rows:
                row = today_rows[ticker]
                hard_stop_price = pos['entry_price'] * (1 - pos['hard_stop_pct'])
                
                exit_price = None
                exit_reason = ""
                
                # 장중 폭락 시 손절
                if row['low'] <= hard_stop_price:
                    exit_price = hard_stop_price
                    exit_reason = "Hard Stop (방어선 붕괴)"
                # 전일 5일선 이탈로 뜬 T+1일 시가 청산
                elif row['execute_exit_T_plus_1'] == True:
                    exit_price = row['open']
                    exit_reason = "추세 이탈 (SMA 5선)"
                    
                if exit_price is not None:
                    profit_amt = pos['qty'] * (exit_price - pos['entry_price'])
                    capital += pos['qty'] * exit_price
                    tickers_to_remove.append(ticker)
                    
                    # 엑셀 다운로드용 트레이딩 로그 적재
                    trade_logs.append({
                        "종목명": ticker,
                        "진입일자": pos['entry_date'],
                        "진입단가": round(pos['entry_price'], 0),
                        "매수수량": int(pos['qty']),
                        "청산일자": current_date,
                        "청산단가": round(exit_price, 0),
                        "청산사유": exit_reason,
                        "수익률(%)": round(((exit_price / pos['entry_price']) - 1) * 100, 2),
                        "수익금액": round(profit_amt, 0)
                    })
                    
        for ticker in tickers_to_remove:
            del positions[ticker]
            
        # [2] 진입 처리
        for ticker in current_target_tickers:
            if ticker not in positions and ticker in today_rows:
                row = today_rows[ticker]
                if row['execute_buy_T_plus_1'] == True:
                    current_portfolio_value = capital
                    for holds_ticker, pos in positions.items():
                        if holds_ticker in today_rows:
                            current_portfolio_value += pos['qty'] * today_rows[holds_ticker]['open']
                            
                    # 매수 비중: 인자로 전달받은 weight_per_ticker 사용
                    target_invest_amount = current_portfolio_value * weight_per_ticker
                    if capital >= target_invest_amount:
                        qty = int(target_invest_amount // row['open'])
                        if qty > 0:
                            capital -= qty * row['open']
                            positions[ticker] = {
                                'qty': qty,
                                'entry_price': row['open'],
                                'entry_date': current_date,
                                'hard_stop_pct': row['hard_stop_loss_pct']
                            }

        # [3] 스크리닝 (주도주 필터링) - [가변 종목 수 지원]
        if is_friday or t_idx == 0:
            # [V3.1.2] 신규모드: composite_rs 우선 순위, 없을 경우 rs_20 사용
            rs_scores = {}
            for ticker, row in today_rows.items():
                score_col = 'composite_rs' if 'composite_rs' in row else 'rs_20'
                if score_col in row and not pd.isna(row[score_col]):
                    rs_scores[ticker] = row[score_col]
            sorted_tickers = sorted(rs_scores.items(), key=lambda x: x[1], reverse=True)
            # 인자로 전달받은 max_tickers 수만큼 슬라이싱
            current_target_tickers = [x[0] for x in sorted_tickers[:max_tickers]]
            
        # [4] 잔고 평가 기록
        daily_value = capital
        for ticker, pos in positions.items():
            if ticker in today_rows:
                daily_value += pos['qty'] * today_rows[ticker]['close']
        portfolio_history.append({'date': current_date, 'total_value': daily_value})
        
    df_history = pd.DataFrame(portfolio_history)
    df_trades = pd.DataFrame(trade_logs)
    
    # [5] MDD (Maximum Drawdown) 계산
    mdd = 0
    if not df_history.empty:
        df_history['peak'] = df_history['total_value'].cummax()
        df_history['drawdown'] = (df_history['total_value'] - df_history['peak']) / df_history['peak']
        mdd = df_history['drawdown'].min() * 100

    final_value = df_history['total_value'].iloc[-1] if not df_history.empty else initial_capital
    cagr = 0
    if not df_history.empty:
        years = (pd.to_datetime(df_history['date'].iloc[-1]) - pd.to_datetime(df_history['date'].iloc[0])).days / 365.25
        years = max(years, 0.5)
        cagr = ((final_value / initial_capital) ** (1 / years) - 1) * 100
        
    # 최종 결과 반환
    if df_history.empty:
        return {
            "initial_capital": initial_capital,
            "final_capital": initial_capital,
            "cumulative_return": 0.0,
            "cagr": 0,
            "mdd": 0,
            "history": df_history,
            "trades_df": df_trades,
            "start_date": "-",
            "end_date": "-",
            "total_days": 0
        }

    return {
        "initial_capital": initial_capital,
        "final_capital": round(final_value, 0),
        "cumulative_return": round((final_value / initial_capital - 1) * 100, 2),
        "cagr": round(cagr, 2),
        "mdd": round(mdd, 2),
        "history": df_history,
        "trades_df": df_trades,
        "start_date": df_history['date'].iloc[0],
        "end_date": df_history['date'].iloc[-1],
        "total_days": len(df_history)
    }
