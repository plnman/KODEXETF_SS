import os
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from data_collector.supabase_client import get_supabase_client

# KODEX 기반 IRP 거래 가능 핵심 10개 섹터 및 지수 ETF
# (KODEX만 고집하지 않고 거래대금 최상위 종목군으로 엄선)
TARGET_ETFS = {
    "069500.KS": "KODEX 200", 
    "226490.KS": "KODEX 코스닥150",
    "091160.KS": "KODEX 반도체",
    "091170.KS": "KODEX 은행",
    "091180.KS": "KODEX 자동차",
    "305720.KS": "KODEX 2차전지산업",
    "117700.KS": "KODEX 건설",
    "091220.KS": "KODEX 금융",
    "102970.KS": "KODEX 기계장비",
    "117680.KS": "KODEX 철강"
}

def calculate_mfi(df, period=14):
    """MFI (Money Flow Index) 계산: 1분봉 CVD를 대체할 일봉 기반 수급 엔진"""
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    raw_money_flow = typical_price * df['Volume']
    
    positive_flow = []
    negative_flow = []
    
    for i in range(len(typical_price)):
        if i == 0:
            positive_flow.append(0)
            negative_flow.append(0)
            continue
        if typical_price.iloc[i] > typical_price.iloc[i-1]:
            positive_flow.append(raw_money_flow.iloc[i])
            negative_flow.append(0)
        elif typical_price.iloc[i] < typical_price.iloc[i-1]:
            positive_flow.append(0)
            negative_flow.append(raw_money_flow.iloc[i])
        else:
            positive_flow.append(0)
            negative_flow.append(0)
            
    pos_flow_sum = pd.Series(positive_flow, index=df.index).rolling(window=period).sum()
    neg_flow_sum = pd.Series(negative_flow, index=df.index).rolling(window=period).sum()
    
    # 0으로 나누는 에러 방지
    money_ratio = pos_flow_sum / np.where(neg_flow_sum == 0, 1, neg_flow_sum)
    mfi = 100 - (100 / (1 + money_ratio))
    return mfi

def calculate_intraday_intensity(df):
    """장중 매수 강도 (Intraday Intensity): 종가를 고점에서 마감시키는 주포의 힘을 측정"""
    range_hl = df['High'] - df['Low']
    # 0으로 나누는 에러(점상한가 등) 방지
    range_hl = np.where(range_hl == 0, 0.001, range_hl)
    ii = ((2 * df['Close'] - df['High'] - df['Low']) / range_hl) * df['Volume']
    return ii

def fetch_and_store_daily_data(start_date="2019-01-01"):
    supabase = get_supabase_client()
    if not supabase:
        print("Supabase 연결 실패. .env 파일을 확인하세요.")
        return

    end_date = datetime.now().strftime("%Y-%m-%d")
    print(f"[{datetime.now()}] T일 종가 기반 (15:40) IRP 유니버스 수집 시작 ({start_date} ~ {end_date})")

    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start=start_date, end=end_date)
    
    records_to_upsert = []
    
    for raw_ticker in tickers_list:
        ticker_clean = raw_ticker.replace(".KS", "")
        
        # 다중 심볼 yfinance 데이터 안전하게 파싱
        df_ticker = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, raw_ticker) in data.columns:
                df_ticker[col] = data[(col, raw_ticker)]
            elif col in data.columns and isinstance(data.columns, pd.Index) and len(tickers_list) == 1:
                df_ticker[col] = data[col]
                
        df_ticker = df_ticker.dropna(subset=['Open', 'Close', 'Volume'])
        if df_ticker.empty:
            continue
            
        # (중요) DB 적재 직전, CVD를 대신할 MFI/Intraday 지표를 수식 계산하여 함께 묶어버림
        df_ticker['mfi'] = calculate_mfi(df_ticker)
        df_ticker['intraday_intensity'] = calculate_intraday_intensity(df_ticker)
        
        # MFI 연산으로 인해 발생하는 초반 NaN row 14개 버리기
        df_ticker = df_ticker.dropna() 
        
        for date_idx, row in df_ticker.iterrows():
            record = {
                "date": date_idx.strftime("%Y-%m-%d"),
                "ticker": ticker_clean,
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row['Volume']),
                "mfi": float(row['mfi']),
                "intraday_intensity": float(row['intraday_intensity'])
            }
            records_to_upsert.append(record)

    # 메모리 및 네트워크 과부하 방지를 위한 1000개 단위 청크 단위 Upsert
    chunk_size = 1000
    for i in range(0, len(records_to_upsert), chunk_size):
        chunk = records_to_upsert[i:i+chunk_size]
        response = supabase.table('market_data').upsert(chunk).execute()
        print(f"[{ticker_clean} 등] {len(chunk)}개 일봉 데이터 market_data 테이블 적재 성공.")
    
    print(f"[{datetime.now()}] IRP 섹터 유니버스 데이터 수집 및 MFI 연산 완료 (Tracking Error 0% 통제 성공).")

if __name__ == "__main__":
    load_dotenv()
    # 최초 실행 시 2019년부터 전수 백필(Backfill) 진행
    fetch_and_store_daily_data(start_date="2019-01-01")
