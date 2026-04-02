import os
import yfinance as yf
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
from datetime import datetime
from dotenv import load_dotenv
from data_collector.supabase_client import get_supabase_client

# KODEX 기반 IRP 거래 가능 핵심 10개 섹터 및 지수 ETF
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
    """MFI (Money Flow Index) 계산: Pandas 정석 로직으로 수학적 무결성 100% 복구"""
    h, l, c, v = df['High'], df['Low'], df['Close'], df['Volume']
    tp = (h + l + c) / 3.0
    mf = tp * v
    tp_diff = tp.diff()
    pos_mf = mf.where(tp_diff > 0, 0.0)
    neg_mf = mf.where(tp_diff < 0, 0.0)
    pos_mf_sum = pos_mf.rolling(window=period).sum()
    neg_mf_sum = neg_mf.rolling(window=period).sum()
    mfr = pos_mf_sum / neg_mf_sum.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mfr.fillna(pos_mf_sum.apply(lambda x: 1000000 if x > 0 else 0))))
    return mfi.fillna(50)

def calculate_intraday_intensity(df):
    """장중 매수 강도 (Intraday Intensity): Pandas 기반의 안전한 스케일링 복구"""
    h, l, c, v = df['High'], df['Low'], df['Close'], df['Volume']
    range_hl = (h - l).replace(0, 0.001)
    ii = ((2 * c - h - l) / range_hl) * v
    return ii

def verify_dual_source_integrity(all_signals):
    """야후(yf) 데이터와 네이버(fdr) 데이터를 교차 검증하여 무결성 점수 산출"""
    try:
        df_naver = fdr.DataReader("069500").tail(5)
        naver_price = float(df_naver['Close'].iloc[-1])
        if "KODEX 200" in all_signals:
            yf_price = float(all_signals["KODEX 200"]['close'].iloc[-1])
            diff_pct = abs(yf_price - naver_price) / naver_price * 100
            if diff_pct < 1.0:
                return {"status": "Pass", "score": 100, "detail": f"데이터 일치 (편차 {diff_pct:.2f}%)"}
            else:
                return {"status": "Fail", "score": 50, "detail": f"데이터 불일계! 편차 {diff_pct:.2f}%"}
    except Exception as e:
        return {"status": "Error", "score": 0, "detail": str(e)}
    return {"status": "Unknown", "score": 0, "detail": "Missing data"}

def fetch_and_store_daily_data(start_date="2019-01-01"):
    supabase = get_supabase_client()
    if not supabase: return
    end_date = datetime.now().strftime("%Y-%m-%d")
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start=start_date, end=end_date)
    records_to_upsert = []
    for raw_ticker in tickers_list:
        ticker_clean = raw_ticker.replace(".KS", "")
        df_ticker = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, raw_ticker) in data.columns: df_ticker[col] = data[(col, raw_ticker)]
        df_ticker = df_ticker.dropna(subset=['Open', 'Close', 'Volume'])
        if df_ticker.empty: continue
        df_ticker['mfi'] = calculate_mfi(df_ticker)
        df_ticker['intraday_intensity'] = calculate_intraday_intensity(df_ticker)
        df_ticker = df_ticker.dropna() 
        for date_idx, row in df_ticker.iterrows():
            record = {
                "date": date_idx.strftime("%Y-%m-%d"), "ticker": ticker_clean,
                "open": float(row['Open']), "high": float(row['High']), "low": float(row['Low']),
                "close": float(row['Close']), "volume": int(row['Volume']),
                "mfi": float(row['mfi']), "intraday_intensity": float(row['intraday_intensity'])
            }
            records_to_upsert.append(record)
    chunk_size = 1000
    for i in range(0, len(records_to_upsert), chunk_size):
        supabase.table('market_data').upsert(records_to_upsert[i:i+chunk_size]).execute()
