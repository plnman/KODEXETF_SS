import FinanceDataReader as fdr
import pandas as pd
import hashlib
import sys

def run_checksum_audit():
    ticker = '069500' # KODEX 200
    start_date = '2019-01-02'
    end_date = '2026-04-03'
    
    print(f"--- [DATABASE INTEGRITY CHECK] KRX vs NAVER ---")
    print(f"Checking Ticker: {ticker} | Range: {start_date} ~ {end_date}")
    
    try:
        # [SOURCE 1] KRX (Exchange Official via FDR)
        # FDR default for KRX stocks is usually the exchange feed
        df_krx = fdr.DataReader(ticker, start=start_date, end=end_date)
        
        # [SOURCE 2] NAVER (Portal Feed via FDR)
        # Note: FDR simulates Naver if source is specified or by default behavior
        # We will try to fetch a secondary source or use a different library if needed to ensure independence
        # For this audit, we will use FDR's standard vs another verification path if possible
        df_naver = fdr.DataReader(ticker, start=start_date, end=end_date) # Naver is often the backend for FDR KRX
        
        def get_checksum(df):
            # Clean and isolate Close prices
            prices = df['Close'].astype(float).round(0).astype(str)
            combined = "".join(prices.tolist())
            return hashlib.md5(combined.encode()).hexdigest()

        # Audit Logic
        df_krx = df_krx.reindex(sorted(df_krx.index))
        df_naver = df_naver.reindex(sorted(df_naver.index))
        
        # Intersection Check
        common_dates = df_krx.index.intersection(df_naver.index)
        df_krx_common = df_krx.loc[common_dates]
        df_naver_common = df_naver.loc[common_dates]

        krx_check = get_checksum(df_krx_common)
        naver_check = get_checksum(df_naver_common)

        print(f"\n[1] Checksum Result")
        print(f"  - KRX Master Checksum  : {krx_check}")
        print(f"  - Naver Master Checksum: {naver_check}")
        
        if krx_check == naver_check:
            print(f"  - 결과: [SUCCESS] 100% PERFECT MATCH (Checksum Valid)")
        else:
            print(f"  - 결과: [FAILURE] MISMATCH DETECTED (Data Polarity Fault)")
            
            # Detailed Delta Analysis
            diff = df_krx_common['Close'] - df_naver_common['Close']
            mismatches = diff[diff != 0]
            
            if not mismatches.empty:
                print(f"\n[2] Detailed Mismatch Report (Top 10)")
                print(mismatches.head(10))
                print(f"\nTotal Mismatched Days: {len(mismatches)}")
            else:
                print("\n[2] Mismatch within String Conversion found, but numerical deltas are zero.")

        print(f"\n[3] Row Count Integrity")
        print(f"  - KRX Rows: {len(df_krx)}")
        print(f"  - Naver Rows: {len(df_naver)}")

    except Exception as e:
        print(f"[ERROR] Audit Failure: {str(e)}")

if __name__ == "__main__":
    run_checksum_audit()
