"""04-17 비정상 체결 진단"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r'C:\Users\kim.ss\Projects\Claude_KODEX_SS\app')

from data_collector.supabase_client import get_supabase_client
sb = get_supabase_client()

# 1. 04-17 buy_signal=True 종목
print("=== 04-17 buy_signal=True 종목 ===")
r = sb.table('daily_signals').select(
    'signal_date,ticker,composite_rs,close,target_break_price,buy_signal,exit_signal'
).eq('signal_date', '2026-04-17').eq('buy_signal', True).execute()
if r.data:
    for row in r.data:
        print(f"  {row['ticker']:30s}  RS={row['composite_rs']:.4f}  종가={row['close']}  목표={row['target_break_price']}")
else:
    print("  없음")

# 2. 04-17 전체 신호
print("\n=== 04-17 전체 신호 (RS 내림차순) ===")
r2 = sb.table('daily_signals').select(
    'signal_date,ticker,composite_rs,close,target_break_price,buy_signal,exit_signal'
).eq('signal_date', '2026-04-17').order('composite_rs', desc=True).execute()
for row in r2.data:
    b = "BUY " if row['buy_signal'] else "    "
    e = "EXIT" if row['exit_signal'] else "    "
    print(f"  {b} {e}  {row['ticker']:30s}  RS={row['composite_rs']:.4f}  종가={row['close']}  목표={row['target_break_price']}")

# 3. 04-17 live_trades 전체
print("\n=== 04-17 live_trades 전체 ===")
r3 = sb.table('live_trades').select('*').eq('execute_date', '2026-04-17').execute()
if r3.data:
    for row in r3.data:
        print(f"  {row}")
else:
    print("  없음")

# 4. 전체 live_trades (최근 10건)
print("\n=== live_trades 전체 (최근 10건) ===")
r4 = sb.table('live_trades').select('*').order('execute_date', desc=True).limit(10).execute()
for row in r4.data:
    print(f"  {row['execute_date']}  {row['action']:4s}  {row['ticker']:25s}  단가={row['price']}  수량={row['quantity']}  금액={row['amount']}")

# 5. live_portfolio (현재 보유)
print("\n=== live_portfolio 전체 ===")
r5 = sb.table('live_portfolio').select('*').execute()
for row in r5.data:
    print(f"  {row}")
