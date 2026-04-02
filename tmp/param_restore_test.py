"""
원본 V3.1 TICKER_PARAMS 복원 효과 검증
- 코드 수정 없이 overrides로 원본 파라미터를 주입하여 수익률 변화 확인
"""
import sys, os
sys.path.insert(0, '.')
import yfinance as yf
import pandas as pd
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.portfolio_backtester import run_portfolio_backtest

# ── 원본 V3.1 파라미터 (018349c 커밋 기준) ──
ORIGINAL_PARAMS = {
    "KODEX 200":         {'k': 0.7, 'mfi': 40, 'adx_threshold': 15},
    "KODEX 코스닥150":   {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 반도체":      {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 은행":        {'k': 0.7, 'mfi': 65, 'adx_threshold': 20},
    "KODEX 자동차":      {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 2차전지산업": {'k': 0.3, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 건설":        {'k': 0.4, 'mfi': 60, 'adx_threshold': 15},
    "KODEX 금융":        {'k': 0.5, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 기계장비":    {'k': 0.7, 'mfi': 65, 'adx_threshold': 15},
    "KODEX 철강":        {'k': 0.3, 'mfi': 40, 'adx_threshold': 15},
}

def load_all_signals(use_original_params=False):
    all_signals = {}
    label = "원본 V3.1" if use_original_params else "현재 (균일)"

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

    overrides_k200 = ORIGINAL_PARAMS["KODEX 200"] if use_original_params else None
    k200_signals = build_signals_and_targets(k200_raw, ticker_name="KODEX 200", overrides=overrides_k200)
    regime_series = get_market_regime(k200_signals)
    all_signals["KODEX 200"] = k200_signals

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
                continue
            df_upper = df_c.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
            df_c['mfi'] = calculate_mfi(df_upper)
            df_c['intraday_intensity'] = calculate_intraday_intensity(df_upper)
            overrides = ORIGINAL_PARAMS.get(name) if use_original_params else None
            sigs = build_signals_and_targets(df_c, ticker_name=name, overrides=overrides, is_bull_market=regime_series)
            all_signals[name] = sigs
        except Exception as e:
            print(f"  [ERR] {name}: {e}")

    return all_signals, label

print("=" * 60)
print("데이터 다운로드 중... (약 1분 소요)")
print("=" * 60)

# ── 현재 파라미터 결과 ──
signals_current, label_c = load_all_signals(use_original_params=False)
print(f"\n[{label_c}] 백테스트 결과:")
for n, w in [(3, 1/3), (5, 0.2), (10, 0.1)]:
    r = run_portfolio_backtest(signals_current, initial_capital=50000000.0, max_tickers=n, weight_per_ticker=w)
    print(f"  {n}종목: 수익률={r['cumulative_return']}%  CAGR={r['cagr']}%  MDD={r['mdd']}%")

# ── 원본 V3.1 파라미터 결과 ──
signals_orig, label_o = load_all_signals(use_original_params=True)
print(f"\n[{label_o}] 백테스트 결과:")
for n, w in [(3, 1/3), (5, 0.2), (10, 0.1)]:
    r = run_portfolio_backtest(signals_orig, initial_capital=50000000.0, max_tickers=n, weight_per_ticker=w)
    print(f"  {n}종목: 수익률={r['cumulative_return']}%  CAGR={r['cagr']}%  MDD={r['mdd']}%")

print("\n=== 비교 완료 ===")
