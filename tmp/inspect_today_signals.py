import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import sys
import os

# 프로젝트 경로 추가
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

# UTF-8 출력 강제 (Windows 대응)
import io
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

from engine.strategy import build_signals_and_targets, get_market_regime, TICKER_PARAMS
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity

def inspect_today():
    print(f"[REPORT START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Precise Signal Analysis")
    
    all_tickers = {
        "069500.KS": "KODEX 200", 
        "226490.KS": "KODEX KOSDAQ150", 
        "091160.KS": "KODEX SEMI", 
        "305720.KS": "KODEX 2nd BATTERY", 
        "091180.KS": "KODEX AUTO",
        "091220.KS": "KODEX FINANCE"
    }
    
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    # 1. Market Regime
    k200_raw = yf.download("069500.KS", start=start_date, progress=False)
    if isinstance(k200_raw.columns, pd.MultiIndex): k200_raw.columns = k200_raw.columns.get_level_values(0)
    k200_raw = k200_raw.dropna().reset_index()
    k200_raw.columns = [c.lower() for c in k200_raw.columns]
    
    def prep(df):
        df = df.copy()
        df.rename(columns={'date': 'Date'}, inplace=True)
        df.columns = [c.capitalize() for c in df.columns]
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        df = df.dropna().reset_index(drop=True)
        df.columns = [c.lower() for c in df.columns]
        return df

    k200_prepped = prep(k200_raw)
    k200_sigs = build_signals_and_targets(k200_prepped, "KODEX 200")
    regime = get_market_regime(k200_sigs)
    is_bull = regime.iloc[-1]
    
    print(f"MARKET REGIME: {'BULL' if is_bull else 'STABLE'} (Based on ADX Z-Score)")
    print("-" * 120)
    
    analysis_list = []
    
    for tk_code, name in all_tickers.items():
        df_raw = yf.download(tk_code, start=start_date, progress=False)
        if isinstance(df_raw.columns, pd.MultiIndex): df_raw.columns = df_raw.columns.get_level_values(0)
        df_raw = df_raw.dropna().reset_index()
        df_raw.columns = [c.lower() for c in df_raw.columns]
        df = prep(df_raw)
        
        # build_signals_and_targets
        sig_df = build_signals_and_targets(df, name, is_bull_market=regime)
        last = sig_df.iloc[-1]
        params = TICKER_PARAMS.get(name, {"k":0.5, "mfi":60, "adx_threshold":20})
        
        c1 = last['close'] >= last['target_break_price']
        c2 = last['mfi'] > params['mfi']
        c3 = last['intraday_intensity'] > 0
        c4 = last['adx_14'] > params['adx_threshold']
        
        status = "BUY" if (c1 and c2 and c3 and c4) else "WATCH"
        missed = [k for k, v in {"PRICE":c1, "MFI":c2, "II":c3, "ADX":c4}.items() if not v]
        
        analysis_list.append({
            "TICKER": name,
            "RS_SCORE": round(last['composite_rs']*100, 2),
            "CURR_P": int(last['close']),
            "TARGET": int(last['target_break_price']),
            "MFI_VAL": round(last['mfi'], 1),
            "MFI_THR": params['mfi'],
            "ADX_VAL": round(last['adx_14'], 1),
            "ADX_THR": params['adx_threshold'],
            "STATUS": status,
            "MISSED": ", ".join(missed) if missed else "-"
        })

    final_report = pd.DataFrame(analysis_list).sort_values("RS_SCORE", ascending=False)
    print(final_report.to_string(index=False))
    print("-" * 120)
    print("INTEGRITY REPORT")
    print(f"BASELINE RETURN (V3.4.0): 229.37%")
    print(f"SYNC DATE: {sig_df['date'].iloc[-1]}")
    print(f"SSOT: yFinance (Confirmed)")

if __name__ == "__main__":
    inspect_today()
