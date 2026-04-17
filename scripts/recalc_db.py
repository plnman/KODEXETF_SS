"""
DB 재계산: 소수점 수량 오류 수정
1. id=4 (반도체 0.90주) 삭제
2. id=5 (나스닥100 0.01주) 삭제
3. id=3 (AI테크TOP10) units=3332 (정수), amount=49,896,700 으로 수정
4. portfolio_history 04-15~04-17 재계산
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r'C:\Users\kim.ss\Projects\Claude_KODEX_SS\app')

import FinanceDataReader as fdr
import pandas as pd
from data_collector.supabase_client import get_supabase_client
sb = get_supabase_client()

# ── AI테크TOP10 일별 종가 조회
print("=== AI테크TOP10 (485540) 가격 확인 ===")
df = fdr.DataReader('485540', '2026-04-10')
df = df.reset_index()
df.columns = [c.lower() for c in df.columns]
df['date_str'] = df['date'].astype(str).str[:10]
price_map = {row['date_str']: row for _, row in df.iterrows()}

for d in ['2026-04-15', '2026-04-16', '2026-04-17']:
    row = price_map.get(d)
    if row is not None:
        print(f"  {d}  open={row['open']}  close={row['close']}")

# ── 수정 계산
INITIAL_CAPITAL = 50_000_000.0
EXECUTE_PRICE   = 14975.0          # id=3 execute_price (04-15 시가)
UNITS_INT       = int(INITIAL_CAPITAL * 0.998 / EXECUTE_PRICE)   # floor
AMOUNT_INT      = UNITS_INT * EXECUTE_PRICE
CASH_AFTER_BUY  = INITIAL_CAPITAL - AMOUNT_INT

print(f"\n=== id=3 수정 계산 ===")
print(f"  execute_price = {EXECUTE_PRICE:,.0f}원")
print(f"  invest        = {INITIAL_CAPITAL*0.998:,.0f}원  (50,000,000 × 0.998)")
print(f"  units (소수)  = {INITIAL_CAPITAL*0.998/EXECUTE_PRICE:.6f}주  → 현재 DB")
print(f"  units (정수)  = {UNITS_INT}주  → 수정 후")
print(f"  amount (정수) = {AMOUNT_INT:,.0f}원")
print(f"  cash 잔액     = {CASH_AFTER_BUY:,.0f}원")

# ── 확인 후 수정
print("\n=== DB 수정 시작 ===")

# 1. id=5 삭제 (나스닥100 199.6원)
r = sb.table('live_trades').delete().eq('id', 5).execute()
print(f"  [DELETE] id=5 KODEX 나스닥100 0.01주 → 삭제 완료")

# 2. id=4 삭제 (반도체 0.90주 — 정수 기준 구매 불가)
r = sb.table('live_trades').delete().eq('id', 4).execute()
print(f"  [DELETE] id=4 KODEX 반도체 0.90주  → 삭제 완료  (잔여현금 {CASH_AFTER_BUY:,.0f}원으로 {110500:,.0f}원 × 1주 미달)")

# 3. id=3 수정 (units 정수화)
r = sb.table('live_trades').update({
    'units':  float(UNITS_INT),
    'amount': float(AMOUNT_INT),
}).eq('id', 3).execute()
print(f"  [UPDATE] id=3 units: 3332.220367 → {UNITS_INT}  |  amount: 49,900,000 → {AMOUNT_INT:,.0f}")

# ── portfolio_history 재계산
print("\n=== portfolio_history 재계산 ===")
for date_str in ['2026-04-15', '2026-04-16', '2026-04-17']:
    row = price_map.get(date_str)
    if row is None:
        print(f"  {date_str}: FDR 데이터 없음 — 스킵")
        continue
    close_price = float(row['close'])
    positions_value = UNITS_INT * close_price
    cash            = CASH_AFTER_BUY
    total_value     = cash + positions_value
    ret_pct         = (total_value / INITIAL_CAPITAL - 1) * 100

    r = sb.table('live_portfolio_history').upsert({
        'date':            date_str,
        'cash':            round(cash, 2),
        'positions_value': round(positions_value, 2),
        'total_value':     round(total_value, 2),
    }, on_conflict='date').execute()
    print(f"  {date_str}  close={close_price:,.0f}  현금={cash:,.0f}  보유={positions_value:,.0f}  총={total_value:,.0f}  {ret_pct:+.2f}%")

# ── 최종 live_trades 확인
print("\n=== 최종 live_trades ===")
r = sb.table('live_trades').select('id,execute_date,action,ticker,units,execute_price,amount').order('id').execute()
for row in r.data:
    print(f"  id={row['id']}  {row['execute_date']}  {row['action']:4s}  {row['ticker']:25s}  {row['units']}주  {row['amount']:,.0f}원")

print("\n[완료]")
