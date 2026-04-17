import sys, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r'C:\Users\kim.ss\Projects\Claude_KODEX_SS\app')
from data_collector.supabase_client import get_supabase_client
sb = get_supabase_client()

print("=== live_trades 전체 ===")
r = sb.table('live_trades').select(
    'id,execute_date,signal_date,action,ticker,units,execute_price,amount,hard_stop_pct'
).order('id').execute()
for row in r.data:
    print(f"  id={row['id']}  {row['execute_date']}  {row['action']:15s}  {row['ticker']:25s}  {row['units']}주  {row['amount']}원")
