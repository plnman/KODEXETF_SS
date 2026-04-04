import os
import sys
from datetime import datetime
import io

# 프로젝트 경로 추가
sys.path.append(os.getcwd())
# UTF-8 출력 강제 (Windows 대응)
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

from data_collector.supabase_client import get_supabase_client

def verify_today_sync():
    supabase = get_supabase_client()
    today_str = "2026-04-03"
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Supabase DB SYNC CHECK")
    
    # 1. backtest_history 내역 확인
    hist_res = supabase.table('backtest_history').select('*').eq('record_date', today_str).execute()
    
    # 2. daily_signals 내역 확인 (오늘 생성된 모든 종목)
    sig_res = supabase.table('daily_signals').select('ticker').eq('signal_date', today_str).execute()
    
    print("-" * 50)
    if hist_res.data:
        print(f"SUCCESS: {today_str} portfolio entry found.")
        print(f"DATA: {hist_res.data[0]}")
    else:
        print(f"FAIL: {today_str} portfolio entry NOT found.")
        
    print("-" * 50)
    if sig_res.data:
        print(f"SUCCESS: {today_str} daily signals found. (Total: {len(sig_res.data)} tickers)")
        tickers = [d['ticker'] for d in sig_res.data]
        print(f"TICKERS: {', '.join(tickers)}")
    else:
        print(f"FAIL: {today_str} daily signals NOT found.")
    print("-" * 50)

if __name__ == "__main__":
    verify_today_sync()
