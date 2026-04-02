import sys, os
sys.path.insert(0, '.')
import yfinance as yf
import pandas as pd
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS
from engine.strategy import build_signals_and_targets, get_market_regime, TICKER_PARAMS
from analytics.portfolio_backtester import run_portfolio_backtest

print("=== [1] TICKER_PARAMS 전체 확인 ===")
for k, v in TICKER_PARAMS.items():
    print(f"  {k}: {v}")

# ---------- KODEX 200 기준 데이터 ----------
print("\n=== [2] 전 종목 데이터 로딩 ===")
all_signals = {}
k200_data = yf.download("069500.KS", start="2019-01-01", progress=False)
if isinstance(k200_data.columns, pd.MultiIndex):
    k200_data.columns = [col[0] for col in k200_data.columns]
k200_raw = k200_data.dropna().reset_index()
k200_raw['date'] = k200_raw['Date'].dt.strftime('%Y-%m-%d')
df_upper_k2 = k200_raw.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
k200_raw['mfi'] = calculate_mfi(df_upper_k2)
k200_raw['intraday_intensity'] = calculate_intraday_intensity(df_upper_k2)
k200_raw = k200_raw.dropna().reset_index(drop=True)
k200_raw = k200_raw.drop(columns=['Date'], errors='ignore')
k200_raw.columns = [c.lower() for c in k200_raw.columns]
k200_signals = build_signals_and_targets(k200_raw, ticker_name="KODEX 200")
regime_series = get_market_regime(k200_signals)
all_signals["KODEX 200"] = k200_signals
print(f"  [OK] KODEX 200: rows={len(k200_signals)}, latest={k200_signals['date'].iloc[-1]}, close={k200_signals['close'].iloc[-1]:,.0f}")

# 최신 시그널 핵심 컬럼 확인
latest = k200_signals.iloc[-1]
print(f"\n=== [3] KODEX 200 최신 시그널 컬럼 점검 ===")
key_cols = ['date','open','close','mfi','intraday_intensity','sma_20','sma_60','rs_20','composite_rs','execute_buy_T_plus_1','execute_exit_T_plus_1','hard_stop_loss_pct','target_break_price']
for col in key_cols:
    val = latest.get(col, 'MISSING')
    print(f"  {col}: {val}")

# ---------- 나머지 종목 ----------
for raw_ticker, name in TARGET_ETFS.items():
    if name == "KODEX 200":
        continue
    try:
        d = yf.download(raw_ticker, start="2019-01-01", progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [col[0] for col in d.columns]
        df_c = d.copy()
        df_c.columns = [c.lower() for c in df_c.columns]
        df_c = df_c.ffill().fillna(0).reset_index()
        df_c.rename(columns={'Date': 'date'}, inplace=True)
        df_c['date'] = pd.to_datetime(df_c['date']).dt.strftime('%Y-%m-%d')
        if df_c.empty:
            print(f"  [SKIP] {name}: empty")
            continue
        df_upper = df_c.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_c['mfi'] = calculate_mfi(df_upper)
        df_c['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        sigs = build_signals_and_targets(df_c, ticker_name=name, is_bull_market=regime_series)
        all_signals[name] = sigs
        lt = sigs.iloc[-1]
        print(f"  [OK] {name}: rows={len(sigs)}, latest={sigs['date'].iloc[-1]}, close={sigs['close'].iloc[-1]:,.0f}, composite_rs={lt.get('composite_rs','N/A'):.4f}")
    except Exception as e:
        print(f"  [ERR] {name}: {e}")

# ---------- 백테스트 3모드 ----------
print("\n=== [4] 3가지 모드 백테스트 결과 ===")
for n, w in [(3, 1/3), (5, 0.2), (10, 0.1)]:
    r = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=n, weight_per_ticker=w)
    print(f"  [{n}종목] 수익률={r['cumulative_return']}%, 최종={r['final_capital']:,.0f}원, CAGR={r['cagr']}%, MDD={r['mdd']}%, 기간={r['start_date']}~{r['end_date']}, 총거래일={r['total_days']}")

print("\n=== 분석 완료 ===")
