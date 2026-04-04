import pandas as pd

# !!! CRITICAL: NEVER TOUCH BACKTEST CALCULATION LOGIC BELOW !!!
# !!! 수익률 연산 산식 절대 수정 금지 - 데이터 소스 변경 효과 측정용 성역 !!!
# -------------------------------------------------------------------------------------

def run_portfolio_backtest(all_signals_dict: dict, initial_capital: float = 10000000.0, max_tickers: int = 3, use_cash_sweep: bool = True) -> dict:
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
                # [V3.4.0 Switching] 더 강한 추세의 종목이 나타나 순위권(Top 3)에서 밀려난 '애매한 종목' 청산
                elif ticker not in current_target_tickers:
                    exit_price = row['open']
                    exit_reason = "주도주 순위 이탈 (Switching)"
                    
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
                        "매입사유": pos.get('buy_reason', '기본 매수'),
                        "진입단가": round(pos['entry_price'], 0),
                        "매수수량": int(pos['qty']),
                        "청산일자": current_date,
                        "매매사유": exit_reason,
                        "청산단가": round(exit_price, 0),
                        "수익률(%)": round(((exit_price / pos['entry_price']) - 1) * 100, 2),
                        "수익금액": round(profit_amt, 0)
                    })
                    
        for ticker in tickers_to_remove:
            del positions[ticker]
            
        # [2] 진입 처리 - 예수금 100% 박멸 (Full Cash Sweep)
        for ticker in current_target_tickers:
            if ticker not in positions and ticker in today_rows:
                row = today_rows[ticker]
                if row['execute_buy_T_plus_1'] == True:
                    # [V3.4.0 박멸 로직] 남은 현금 100% 투입 (0.2% 버퍼 제외)
                    target_invest_amount = capital * 0.998
                    
                    if capital >= target_invest_amount > 0:
                        qty = int(target_invest_amount // row['open'])
                        if qty > 0:
                            capital -= qty * row['open']
                            
                            buy_reason = "기본 돌파 매수"
                            if row.get('is_bull_market', False) == True:
                                buy_reason = "Turbo-K 가속 진입 (유동성 확인)"
                                
                            positions[ticker] = {
                                'qty': qty,
                                'entry_price': row['open'],
                                'entry_date': current_date,
                                'hard_stop_pct': row['hard_stop_loss_pct'],
                                'buy_reason': buy_reason
                            }

        # [3] 스크리닝 (주도주 필터링) - [매일 스위칭 모드]
        # [V3.4.0] 금요일 제한 없이 매일 갱신하여 강한 추세 발생 시 즉시 포착
        rs_scores = {}
        for ticker, row in today_rows.items():
            score_col = 'composite_rs' if 'composite_rs' in row else 'rs_20'
            if score_col in row and not pd.isna(row[score_col]):
                rs_scores[ticker] = row[score_col]
        sorted_tickers = sorted(rs_scores.items(), key=lambda x: x[1], reverse=True)
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
