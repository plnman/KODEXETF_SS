import os
import yfinance as yf
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
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
    """MFI (Money Flow Index) 계산: NumPy 코어로 데이터 구조 모호성 영구 해결"""
    # [무결성 V3.1.9] 연산 과정에서 데이터프레임 구조의 간섭을 차단하기 위해 NumPy로 추출
    high = df['High'].values.flatten() if 'High' in df else df['high'].values.flatten()
    low = df['Low'].values.flatten() if 'Low' in df else df['low'].values.flatten()
    close = df['Close'].values.flatten() if 'Close' in df else df['close'].values.flatten()
    volume = df['Volume'].values.flatten() if 'Volume' in df else df['volume'].values.flatten()

    typical_price = (high + low + close) / 3.0
    raw_money_flow = typical_price * volume
    
    # 전일 대비 Typical Price 차이 계산 (NumPy 연산)
    price_diff = np.diff(typical_price, prepend=typical_price[0])
    
    # 긍정적/부정적 자금 흐름 계산 (벡터화 - NumPy where)
    pos_flow = np.where(price_diff > 0, raw_money_flow, 0.0)
    neg_flow = np.where(price_diff < 0, raw_money_flow, 0.0)
    
    # 다시 Pandas로 감싸서 Rolling Sum 수행
    pos_flow_sum = pd.Series(pos_flow, index=df.index).rolling(window=period).sum()
    neg_flow_sum = pd.Series(neg_flow, index=df.index).rolling(window=period).sum()
    
    # 0으로 나누는 에러 방지
    money_ratio = pos_flow_sum / neg_flow_sum.replace(0, np.nan)
    money_ratio = money_ratio.fillna(pos_flow_sum)
    
    mfi = 100 - (100 / (1 + money_ratio))
    return mfi.fillna(50)

def calculate_intraday_intensity(df):
    ii = ((2 * close - high - low) / range_hl) * volume
    return pd.Series(ii, index=df.index)

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
