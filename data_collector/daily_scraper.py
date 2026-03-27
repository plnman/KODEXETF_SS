import sys
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# 모듈 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)

from data_collector.supabase_client import get_supabase_client

# KODEX 백테스팅을 위한 필수 타겟 종목 정의
TARGET_TICKERS = {
    "122630": {"name": "KODEX 레버리지", "is_leverage": True, "is_inverse": False},
    "114800": {"name": "KODEX 인버스", "is_leverage": False, "is_inverse": True},
    "252670": {"name": "KODEX 200선물인버스2X", "is_leverage": True, "is_inverse": True},
    "069500": {"name": "KODEX 200", "is_leverage": False, "is_inverse": False}
}

def init_tickers_in_db(supabase):
    print("\n[Sys] DB에 Ticker 기본 정보를 초기화합니다...")
    for symbol, info in TARGET_TICKERS.items():
        data = {
            "symbol": symbol,
            "name": info["name"],
            "is_leverage": info["is_leverage"],
            "is_inverse": info["is_inverse"],
            "is_active": True
        }
        try:
            supabase.table("tickers").upsert(data).execute()
            print(f"등록 성공: {info['name']}({symbol})")
        except Exception as e:
            print(f"에러 발생 [{symbol}]: {e}")

def fetch_and_store_daily_data(supabase, symbol: str, ticker_name: str, years: int = 5):
    print(f"\n[Scraper] {ticker_name}({symbol}) 과거 데이터(일봉) 수집 시작...")
    yf_symbol = f"{symbol}.KS"
    end_date = datetime.now()
    
    # 2008 & 2020 금융위기 데이터를 포함하려면 강제로 18년(2008년 이후) 데이터를 가져옵니다.
    # 사용자가 요구한 Crisis Stress Test를 위해 과거 데이터를 포함하여 가져옵니다.
    # ETF 상장일 이전의 데이터는 yfinance에서 자동으로 걸러줍니다.
    test_years = max(years, 18)  
    start_date = end_date - timedelta(days=365 * test_years)

    df = yf.download(yf_symbol, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"), progress=False)
    
    if df.empty:
        print(f"[{symbol}] 다운로드 된 데이터가 없습니다.")
        return

    # 다중 인덱스 컬럼 처리 (yfinance 최신 버전 대응)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
        
    df = df.reset_index()
    
    # DB 스키마에 맞게 컬럼명 리네임
    df.rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume"
    }, inplace=True)

    records = []
    for _, row in df.iterrows():
        # 결측치 무시
        if pd.isna(row['open']) or pd.isna(row['close']):
            continue
            
        record = {
            "symbol": symbol,
            "date": row['date'].strftime("%Y-%m-%d"),
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close']),
            "volume": int(row['volume'])
        }
        records.append(record)

    # API를 통해 DB에 일괄 삽입(Upsert)
    batch_size = 1000
    total_inserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        try:
            # ON CONFLICT 설정이 동작하려면 DB에 UNIQUE(symbol, date) 제약조건이 필수입니다.
            supabase.table("daily_ohlcv").upsert(batch, on_conflict="symbol, date").execute()
            total_inserted += len(batch)
            print(f"  -> Batch Upsert: {total_inserted}/{len(records)} rows 완료")
        except Exception as e:
            print(f"  -> API 에러 발생 [{symbol}]: {e}")
            
    print(f"[{symbol}] 데이터 적재 완료 (총 {total_inserted} rows)")

if __name__ == "__main__":
    client = get_supabase_client()
    init_tickers_in_db(client)
    
    for symbol, info in TARGET_TICKERS.items():
        fetch_and_store_daily_data(client, symbol, info['name'])
        
    print("\n✅ [SUCCESS] 5년 전수 데이터 및 금융위기 테스트 파이프라인 적재가 완료되었습니다.")
