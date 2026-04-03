import pandas as pd
import yfinance as yf
from datetime import datetime
import sys
import os

sys.path.append(os.getcwd())
from engine.strategy import build_signals_and_targets, get_market_regime
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import TARGET_ETFS, calculate_mfi, calculate_intraday_intensity

def run_config(all_data, k200_df, config_name, use_cash_sweep, turbo_discount, use_global_mfi):
    # 1. 레짐 판독
    k200_sigs = build_signals_and_targets(k200_df, "KODEX 200", turbo_discount=turbo_discount)
    regime = get_market_regime(k200_sigs, use_global_mfi=use_global_mfi)
    
    all_signals = {}
    for name, df in all_data.items():
        df_sync = df.set_index('date').reindex(k200_df.set_index('date').index).reset_index().ffill().fillna(0)
        df_sync = df_sync.drop_duplicates(subset=['date'])
        
        # 전략 실행 (내부에 np.where 등 모든 신규 로직 반영됨)
        sig = build_signals_and_targets(df_sync, name, is_bull_market=regime, turbo_discount=turbo_discount)
        all_signals[name] = sig

    # 3. 박멸 엔진 호출
    res = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=3, use_cash_sweep=use_cash_sweep)
    
    return res['cumulative_return'], res['mdd']

def main():
    print("[V3.4.0 Final] 진보 과정 4-Way 철저 검증 (실전 엔진 100% 매칭)")
    
    start_date = "2019-01-01"
    all_data = {}
    for tk, name in TARGET_ETFS.items():
        df = yf.download(tk, start=start_date, progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        df = df.dropna()
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns] 
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        all_data[name] = df

    k200_df = all_data["KODEX 200"]

    results = []
    
    # 1. Base (V3.3.5)
    ret, mdd = run_config(all_data, k200_df, "Base", False, 1.0, False)
    results.append({"Configuration": "1. Base (V3.3.5)", "Return(%)": ret, "MDD(%)": mdd})
    
    # 2. 박멸 (Sweep)
    ret, mdd = run_config(all_data, k200_df, "Sweep", True, 1.0, False)
    results.append({"Configuration": "2. 박멸 (Sweep)", "Return(%)": ret, "MDD(%)": mdd})
    
    # 3. 박멸 + 터보 (Sweep + Turbo)
    ret, mdd = run_config(all_data, k200_df, "Sweep + Turbo", True, 0.5, False)
    results.append({"Configuration": "3. 박멸 + 터보", "Return(%)": ret, "MDD(%)": mdd})
    
    # 4. 박멸 + 터보 + 유동성 (V3.4.0)
    ret, mdd = run_config(all_data, k200_df, "Sweep + Turbo + MFI", True, 0.5, True)
    results.append({"Configuration": "4. 박멸 + 터보 + 유동성", "Return(%)": ret, "MDD(%)": mdd})
    
    df_res = pd.DataFrame(results)
    
    print("\n" + "="*60)
    print(" [결과] KODEX IRP 알고리즘 진화 성적표 (Real Engine) ")
    print("="*60)
    print(df_res.to_string(index=False))
    print("="*60)

if __name__ == "__main__":
    main()
