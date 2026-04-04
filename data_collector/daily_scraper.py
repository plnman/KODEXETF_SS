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

def extract_series(df, col_name):
    """MultiIndex DataFrame에서 단일 Series를 안전하게 추출 (V3.3.3 핵심 병기)"""
    if col_name in df.columns:
        res = df[col_name]
        if isinstance(res, pd.DataFrame):
            return res.iloc[:, 0]  # 다중 컬럼일 경우 첫 번째만 취합
        return res
    # 대소문자 방어 로직
    col_lower = col_name.lower()
    for c in df.columns:
        if (isinstance(c, str) and c.lower() == col_lower) or (isinstance(c, tuple) and c[0].lower() == col_lower):
            res = df[c]
            return res.iloc[:, 0] if isinstance(res, pd.DataFrame) else res
    return pd.Series(dtype=float)

def calculate_mfi(df, period=14):
    """MFI (Money Flow Index) 계산: 데이터 구조 모호성(Ambiguity) 영구 해결 버전"""
    # [무결성 V3.3.3] 모든 입력을 강제로 1차원 Series로 변환하여 ValueError 원천 차단
    h = extract_series(df, 'High')
    l = extract_series(df, 'Low')
    c = extract_series(df, 'Close')
    v = extract_series(df, 'Volume')
    
    tp = (h + l + c) / 3.0
    mf = tp * v
    tp_diff = tp.diff()
    
    pos_mf = mf.where(tp_diff > 0, 0.0)
    neg_mf = mf.where(tp_diff < 0, 0.0)
    
    pos_mf_sum = pos_mf.rolling(window=period).sum()
    neg_mf_sum = neg_mf.rolling(window=period).sum()
    
    # 0으로 나누기 방지 및 무결성 보정
    mfr = pos_mf_sum / neg_mf_sum.replace(0, np.nan)
    # 에러를 유발했던 .apply()를 np.where()로 대체하여 매핑 모호성 제거
    mfr_filled = mfr.fillna(pd.Series(np.where(pos_mf_sum > 0, 1000000.0, 0.0), index=df.index))
    
    mfi = 100 - (100 / (1 + mfr_filled))
    return mfi.fillna(50)

def calculate_intraday_intensity(df):
    """장중 매수 강도 (Intraday Intensity): 1차원 Series 강제 압착 버전"""
    h = extract_series(df, 'High')
    l = extract_series(df, 'Low')
    c = extract_series(df, 'Close')
    v = extract_series(df, 'Volume')
    
    range_hl = (h - l).replace(0, 0.001)
    ii = ((2 * c - h - l) / range_hl) * v
    return ii

def verify_dual_source_integrity(all_signals):
    """야후(yf) 데이터와 네이버(fdr) 데이터를 교차 검증하여 무결성을 대조하는 V3.5.0 투트랙 신호등 로직"""
    try:
        supabase = get_supabase_client()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # [1] DB에서 오늘 기록된 Naver vs YF 수익률 대조 (History Tracker)
        yf_hist = supabase.table('backtest_history').select('cumulative_return').eq('record_date', today_str).execute()
        nv_hist = supabase.table('backtest_history_naver').select('cumulative_return').eq('record_date', today_str).execute()
        
        hist_match = False
        if yf_hist.data and nv_hist.data:
            diff = abs(float(yf_hist.data[0]['cumulative_return']) - float(nv_hist.data[0]['cumulative_return']))
            if diff < 0.01:
                hist_match = True
                
        # [2] 오늘자 KODEX 200 실물 시세 즉각 대조 (Live Price Tracker)
        df_naver = fdr.DataReader("069500").tail(1)
        naver_price = float(df_naver['Close'].iloc[-1])
        
        if "KODEX 200" in all_signals:
            yf_price = float(all_signals["KODEX 200"]['close'].iloc[-1])
            price_diff_pct = abs(yf_price - naver_price) / naver_price * 100
        else:
            price_diff_pct = 999.0
            
        # 🚦 신호등 로직 판정 (Traffic Light)
        if price_diff_pct < 2.0 and hist_match:
            return {"status": "🟢 GREEN", "score": 100, "detail": f"완벽 동기화 (가격 오차 {price_diff_pct:.2f}%, DB수익률 일치)"}
        elif price_diff_pct < 2.0 and not hist_match:
            return {"status": "🟡 YELLOW", "score": 85, "detail": f"가격은 일치({price_diff_pct:.2f}%)하나, DB 백테스트 기록 미스매치 (16시 대기중)"}
        else:
            return {"status": "🔴 RED", "score": 0, "detail": f"위험: 시세 오차 {price_diff_pct:.2f}% 또는 원천 데이터 손상"}
            
    except Exception as e:
        return {"status": "🔴 RED", "score": 0, "detail": f"검증 에러: {str(e)}"}

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
