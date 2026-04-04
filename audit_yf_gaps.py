import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd

def audit_missing_dates():
    start, end = '2019-01-01', '2026-04-03'
    # 069500.KS = KODEX 200
    print("Fetching master data from both sources...")
    df_yf = yf.download('069500.KS', start=start, end=end, progress=False)
    df_fdr = fdr.DataReader('069500', start=start, end=end)
    
    # Identify dates FDR has but YF is missing
    diff_dates = df_fdr.index.difference(df_yf.index)
    print(f"Number of suspected missing dates in Yahoo: {len(diff_dates)}\n")
    
    results = []
    for d in diff_dates:
        d_str = d.strftime('%Y-%m-%d')
        # Download one day strictly
        d_next = (d + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        yf_row = yf.download('069500.KS', start=d_str, end=d_next, progress=False)
        
        status = "EMPTY / NO DATA" if yf_row.empty else "DATA FOUND"
        results.append({
            'Date': d_str,
            'Day': d.day_name(),
            'Yahoo Status': status
        })
    
    report = pd.DataFrame(results)
    print("--- RAW PROOF: YAHOO'S RESPONSE FOR SUSPECTED DATES ---")
    print(report.to_string(index=False))

if __name__ == "__main__":
    audit_missing_dates()
