import pandas as pd
import yfinance as yf
import sys
import os

# 현재 경로 추가
sys.path.append(os.getcwd())
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

# [1] Legacy Params (추세 필터 도입 전 실제 쓰이던 파라미터)
LEGACY_PARAMS = {
    "KODEX 200": {'k': 0.7, 'mfi': 40, 'adx_threshold': 15},
    "KODEX 코스닥150": {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 반도체": {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 은행": {'k': 0.7, 'mfi': 65, 'adx_threshold': 20},
    "KODEX 자동차": {'k': 0.2, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 2차전지산업": {'k': 0.3, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 건설": {'k': 0.4, 'mfi': 60, 'adx_threshold': 15},
    "KODEX 금융": {'k': 0.5, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 기계장비": {'k': 0.7, 'mfi': 65, 'adx_threshold': 15},
    "KODEX 철강": {'k': 0.3, 'mfi': 40, 'adx_threshold': 15},
}

# [2] Current Specs (V3.1.3 Optimized)
CURR_SPEC = {'k': 0.4, 'mfi': 55, 'adx_threshold': 15}

def solve_integrity():
    # 데이터 로드
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2019-01-01", progress=False)
    
    cleaned_data_map = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = data.xs(raw_ticker, level=1, axis=1).ffill().dropna().reset_index()
        df_clean.rename(columns={'Date': 'date'}, inplace=True)
        df_clean.columns = [c.lower() for c in df_clean.columns]
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        cleaned_data_map[name] = df_clean

    # --- CASE 1: 순수 수익률 랭킹 (Old RS) + 이전 파라미터 ---
    signals_v2 = {}
    for name, df in cleaned_data_map.items():
        # Composite RS 사용 안 함 (강제 rs_20 만 사용하도록 build_signals 내부 로직 우회 처리된 데이터 준비)
        df_v2 = df.copy()
        # build_signals_and_targets 내부에서 composite_rs를 생성하므로, 백테스트 단계에서 rs_20 강제 선택
        signals_v2[name] = build_signals_and_targets(df_v2, ticker_name=name, overrides=LEGACY_PARAMS[name])
        # 백테스터는 composite_rs가 있으면 그걸 쓰므로, 테스트를 위해 명시적으로 컬럼 삭제
        if 'composite_rs' in signals_v2[name].columns:
            signals_v2[name] = signals_v2[name].drop(columns=['composite_rs'])

    res_v2 = run_portfolio_backtest(signals_v2, max_tickers=3, weight_per_ticker=0.33)

    # --- CASE 2: 추세 필터(Composite RS) + 이전 파라미터 ---
    signals_v311 = {}
    for name, df in cleaned_data_map.items():
        signals_v311[name] = build_signals_and_targets(df.copy(), ticker_name=name, overrides=LEGACY_PARAMS[name])
    res_v311 = run_portfolio_backtest(signals_v311, max_tickers=3, weight_per_ticker=0.33)

    # [V3.1.2] 시장 레짐 판독 (K200 기준)
    k200_raw = cleaned_data_map["KODEX 200"].copy()
    k200_signals = build_signals_and_targets(k200_raw, ticker_name="KODEX 200")
    regime_series = get_market_regime(k200_signals)

    # --- CASE 3: 추세 필터(Composite RS) + 현재 최적 파라미터(V3.1.3) + 시장 레짐(Regime) 주입 ---
    signals_v313 = {}
    for name, df in cleaned_data_map.items():
        signals_v313[name] = build_signals_and_targets(df.copy(), ticker_name=name, overrides=CURR_SPEC, is_bull_market=regime_series)
    res_v313 = run_portfolio_backtest(signals_v313, max_tickers=3, weight_per_ticker=0.33)

    def to_ret(val): return (val / 50000000 - 1) * 100

    print(f"CASE_V2|{to_ret(res_v2['final_capital']):.2f}")
    print(f"CASE_V311|{to_ret(res_v311['final_capital']):.2f}")
    print(f"CASE_V313|{to_ret(res_v313['final_capital']):.2f}")

if __name__ == "__main__":
    solve_integrity()
