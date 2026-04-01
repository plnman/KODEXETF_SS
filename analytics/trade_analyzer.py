import yfinance as yf
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS
import warnings
warnings.filterwarnings('ignore')

def analyze_trades():
    sys.stdout.reconfigure(encoding='utf-8')
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2019-01-01", progress=False)
    
    all_signals = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, raw_ticker) in data.columns:
                df_clean[col.lower()] = data[(col, raw_ticker)]
            elif col in data.columns and len(tickers_list) == 1:
                df_clean[col.lower()] = data[col]
        if df_clean.empty: continue
            
        df_clean = df_clean.dropna().reset_index()
        df_clean['date'] = df_clean['Date'].dt.strftime('%Y-%m-%d')
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        df_clean = df_clean.dropna().reset_index(drop=True)
        signals = build_signals_and_targets(df_clean, ticker_name=name)
        all_signals[name] = signals

    port_res = run_portfolio_backtest(all_signals, initial_capital=50000000.0)
    trades_df = port_res.get('trades_df', pd.DataFrame())
    
    if trades_df.empty:
        print("거래 내역이 존재하지 않습니다.")
        return
        
    trades_df['진입일자'] = pd.to_datetime(trades_df['진입일자'])
    trades_df['청산일자'] = pd.to_datetime(trades_df['청산일자'])
    trades_df['보유기간'] = (trades_df['청산일자'] - trades_df['진입일자']).dt.days
    
    total_trades = len(trades_df)
    win_trades = len(trades_df[trades_df['수익률(%)'] > 0])
    loss_trades = len(trades_df[trades_df['수익률(%)'] <= 0])
    avg_holding = trades_df['보유기간'].mean()
    max_holding = trades_df['보유기간'].max()
    min_holding = trades_df['보유기간'].min()
    
    reason_counts = trades_df['청산사유'].value_counts()
    
    short_trades = trades_df[trades_df['보유기간'] <= 5]
    short_loss = short_trades[short_trades['수익률(%)'] <= 0]
    
    print("=== 📊 실전 거래 데이터 원장 기반 딥다이브 분석 ===")
    print(f"1. 총 거래 횟수: {total_trades}회 (1년에 평균 {(total_trades/5):.1f}회 진입)")
    print(f"2. 전체 트레이딩 승률: {(win_trades/total_trades)*100:.1f}% (수익 {win_trades}회 / 손실 {loss_trades}회)")
    print(f"3. 평균 종목 보유 기간: {avg_holding:.1f}일 (최단 {min_holding}일 ~ 최장 {max_holding}일)")
    print("\n[청산 사유별 상세 비율 및 효율성]")
    for reason, count in reason_counts.items():
        avg_ret = trades_df[trades_df['청산사유'] == reason]['수익률(%)'].mean()
        print(f" - {reason}: {count}회 발생 (이 사유로 청산 시 평균 수익률: {avg_ret:.2f}%)")
        
    print("\n[🚨 잦은 거래(Whipsaw) 및 타점 문제점 진단]")
    print(f" - 진입 후 고작 '5일 이내'에 급하게 잘려나간 횟수: {len(short_trades)}회 (전체 거래의 {(len(short_trades)/total_trades)*100:.1f}%)")
    print(f" - 그 초단기 청산 중 헛스윙(손실 마감) 쳐버린 비율: {(len(short_loss)/len(short_trades)*100) if len(short_trades)>0 else 0:.1f}%")
    print("ANALYSIS_END")

if __name__ == "__main__":
    analyze_trades()
