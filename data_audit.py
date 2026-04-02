import yfinance as yf
import pandas as pd
import sys
import os

# 현재 경로 추가
sys.path.append(os.getcwd())
from data_collector.daily_scraper import TARGET_ETFS

def audit_data():
    print("[DATA INTEGRITY AUDIT] KODEX ETF Data Start Point Analysis")
    print("-" * 60)
    
    tickers_list = list(TARGET_ETFS.keys())
    # 2012년부터 넉넉하게 데이터 수집
    data = yf.download(tickers_list, start="2012-01-01", progress=False)

    if data.empty:
        print("Error: No data downloaded from yfinance.")
        return
    
    audit_results = []
    
    for raw_ticker, name in TARGET_ETFS.items():
        # 종목별 첫 데이터가 있는 날짜 확인
        ticker_close = data['Close'][raw_ticker].dropna()
        if not ticker_close.empty:
            start_date = ticker_close.index[0].strftime("%Y-%m-%d")
            end_date = ticker_close.index[-1].strftime("%Y-%m-%d")
            row_count = len(ticker_close)
            
            audit_results.append({
                "TickerName": name,
                "StartDate": start_date,
                "EndDate": end_date,
                "Count": row_count
            })
            
    df_audit = pd.DataFrame(audit_results).sort_values("StartDate", ascending=False)
    print(df_audit.to_string(index=False))
    
    latest_starter = df_audit.iloc[0]['TickerName']
    latest_start_date = df_audit.iloc[0]['StartDate']
    
    print("-" * 60)
    print(f"CULPRIT IDENTIFIED: [{latest_starter}] started at {latest_start_date}.")
    print(f"Warning: Current dropna() logic truncates ALL backtests before {latest_start_date}.")
    print("-" * 60)

if __name__ == "__main__":
    audit_data()
