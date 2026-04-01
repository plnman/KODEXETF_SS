import pandas as pd
import yfinance as yf
import sys
import os
import numpy as np
import warnings

warnings.filterwarnings('ignore')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine.strategy as strategy_v2
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS

def build_signals_v3_1_hybrid(df_map):
    """
    V3.1 하이브리드 엔진 시뮬레이션: 
    시장(K200)의 ADX Z-Score를 기반으로 V2/V3 모드를 실시간 스위칭합니다.
    """
    # 1. 시장(KODEX 200)의 레짐 판독
    k200_raw = df_map['KODEX 200'].copy()
    k200_signals = strategy_v2.build_signals_and_targets(k200_raw, ticker_name='KODEX 200')
    
    window = 252
    k200_signals['adx_mean'] = k200_signals['adx_14'].rolling(window=window).mean()
    k200_signals['adx_std'] = k200_signals['adx_14'].rolling(window=window).std()
    k200_signals['adx_zscore'] = (k200_signals['adx_14'] - k200_signals['adx_mean']) / k200_signals['adx_std']
    
    # 히스테리시스 레짐 판독 로직
    regime = [] # True: Bull(V3), False: Stable(V2)
    current_bull = False
    for z in k200_signals['adx_zscore']:
        if pd.isna(z):
            regime.append(False)
            continue
        if not current_bull and z > 2.0:
            current_bull = True
        elif current_bull and z < 1.0:
            current_bull = False
        regime.append(current_bull)
    
    k200_signals['is_bull_mode'] = regime
    # 내일 매매에 적용하기 위해 shift(1)
    k200_signals['target_regime_T_plus_1'] = k200_signals['is_bull_mode'].shift(1).fillna(False)
    
    regime_map = k200_signals.set_index('date')['target_regime_T_plus_1'].to_dict()

    # 2. 전 종목 시그널 생성 (레짐에 따라 다이내믹하게)
    all_signals = {}
    for name, df in df_map.items():
        # 기본 V2 시그널 생성 (SMA 10 등 추가 지표 확보 목적)
        df_v3_base = df.copy()
        df_v3_base['sma_10'] = df_v3_base['close'].rolling(window=10).mean()
        
        # V2 시그널
        v2_sig = strategy_v2.build_signals_and_targets(df.copy(), ticker_name=name)
        
        # V3 시그널 (공격형) - 내부 로직 재현
        v3_sig = v2_sig.copy()
        v3_sig['sma_10'] = v3_sig['close'].rolling(window=10).mean()
        
        # V3 진입 로직: K값 20% 할인
        params = strategy_v2.TICKER_PARAMS.get(name, {"k": 0.5})
        k_base = params['k']
        v3_sig['k_adj_v3'] = v3_sig['k_adj'] * 0.8
        v3_sig['target_break_v3'] = v3_sig['open'] + (v3_sig['prev_range'] * v3_sig['k_adj_v3'])
        v3_sig['buy_signal_v3'] = (v3_sig['close'] > v3_sig['target_break_v3']) & (v3_sig['mfi'] > params.get('mfi', 60)) & (v3_sig['intraday_intensity'] > 0) & (v3_sig['adx_14'] > params.get('adx_threshold', 15))
        
        # V3 청산 로직: SMA 10 (강세장 과열 시)
        v3_sig['exit_signal_v3'] = v3_sig['close'] < v3_sig['sma_10']
        
        # 하이브리드 결합
        hybrid = v2_sig.copy()
        for idx, row in hybrid.iterrows():
            d = row['date']
            is_bull = regime_map.get(d, False)
            
            if is_bull:
                # 불장 모드: V3 로직 적용
                hybrid.at[idx, 'execute_buy_T_plus_1'] = v3_sig.at[idx, 'buy_signal_v3']
                hybrid.at[idx, 'execute_exit_T_plus_1'] = v3_sig.at[idx, 'exit_signal_v3']
            else:
                # 일반 모드: 기존 V2 유지
                pass
        
        all_signals[name] = hybrid
        
    return all_signals

def run_hybrid_comparison():
    print("🚀 [V2(현행) vs V3.1(하이브리드) 7년 수익률 진검승부]")
    
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2018-12-20", end="2026-03-31", progress=False)
    
    clean_dfs = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df = data.xs(raw_ticker, axis=1, level=1).dropna().reset_index()
        df.columns = [c.lower() for c in df.columns]
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        df_upper = df.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df['mfi'] = calculate_mfi(df_upper)
        df['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        clean_dfs[name] = df.dropna().reset_index(drop=True)

    # 1. V2 (안정형)
    signals_v2 = {}
    for name, df in clean_dfs.items():
        signals_v2[name] = strategy_v2.build_signals_and_targets(df.copy(), ticker_name=name)
    
    # 2. V3.1 (하이브리드)
    signals_v3_1 = build_signals_v3_1_hybrid(clean_dfs)

    # 백테스트 실행
    res_v2 = run_portfolio_backtest(signals_v2, initial_capital=50000000.0)
    res_v3_1 = run_portfolio_backtest(signals_v3_1, initial_capital=50000000.0)

    # 통계 추출
    def get_metrics(res_dict):
        hist = res_dict['history'].copy()
        hist['date'] = pd.to_datetime(hist['date'])
        hist['year'] = hist['date'].dt.year
        cum_max = hist['total_value'].cummax()
        drawdown = (hist['total_value'] - cum_max) / cum_max
        mdd = drawdown.min() * 100
        annual = {}
        for y in sorted(hist['year'].unique()):
            year_hist = hist[hist['year'] == y]
            annual[y] = (year_hist['total_value'].iloc[-1] / year_hist['total_value'].iloc[0] - 1) * 100
        return annual, mdd, (res_dict['final_capital']/res_dict['initial_capital']-1)*100

    v2_ann, v2_mdd, v2_tot = get_metrics(res_v2)
    v3_ann, v3_mdd, v3_tot = get_metrics(res_v3_1)

    print("\n" + "="*65)
    print(f"{'연도':^6} | {'V2(현행) 수익':^12} | {'V3.1(하이브리드) 수익':^16} | {'Alpha':^10}")
    print("-" * 65)
    for y in sorted(v2_ann.keys()):
        print(f"{y:^8} | {v2_ann[y]:^14.2f}% | {v3_ann[y]:^20.2f}% | {v3_ann[y]-v2_ann[y]:+^12.2f}%")
    print("-" * 65)
    print(f"{'누적 합계':^6} | {v2_tot:^14.2f}% | {v3_tot:^20.2f}% | {v3_tot-v2_tot:+^12.2f}%")
    print(f"{'MDD':^6} | {v2_mdd:^14.2f}% | {v3_mdd:^20.2f}% | {v3_mdd-v2_mdd:+^12.2f}%")
    print("="*65)

if __name__ == "__main__":
    run_hybrid_comparison()
