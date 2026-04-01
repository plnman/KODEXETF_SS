import yfinance as yf
import sys
import pandas as pd
from engine.strategy import build_signals_and_targets
from analytics.portfolio_backtester import run_portfolio_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS
import warnings
warnings.filterwarnings('ignore')

def run_annual_report():
    sys.stdout.reconfigure(encoding='utf-8')
    
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2018-12-25", end="2026-12-31", progress=False)
    
    all_signals = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, raw_ticker) in data.columns:
                df_clean[col.lower()] = data[(col, raw_ticker)]
            elif col in data.columns and len(tickers_list) == 1:
                df_clean[col.lower()] = data[col]
        if df_clean.empty:
            continue
            
        df_clean = df_clean.dropna().reset_index()
        df_clean['date'] = df_clean['Date'].dt.strftime('%Y-%m-%d')
        
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        df_clean = df_clean.dropna().reset_index(drop=True)
        
        signals = build_signals_and_targets(df_clean, ticker_name=name)
        all_signals[name] = signals
        
    port_res = run_portfolio_backtest(all_signals, initial_capital=50000000.0)
    
    df_hist = port_res['history'].copy()
    df_hist['date'] = pd.to_datetime(df_hist['date'])
    df_hist['year'] = df_hist['date'].dt.year
    
    bm_df = all_signals.get("KODEX 200")
    if bm_df is not None:
        bm_df = bm_df.copy()
        bm_df['date'] = pd.to_datetime(bm_df['date'])
        bm_df['year'] = bm_df['date'].dt.year
    
    annual_results = []
    years = sorted(df_hist['year'].unique())
    
    prev_val = port_res['initial_capital']
    bm_prev_close = None
    
    for y in years:
        year_hist = df_hist[df_hist['year'] == y]
        if year_hist.empty:
            continue
            
        end_val = year_hist['total_value'].iloc[-1]
        port_ret = (end_val / prev_val - 1) * 100
        
        bm_ret = 0.0
        if bm_df is not None:
            bm_year = bm_df[bm_df['year'] == y]
            if not bm_year.empty:
                end_price = bm_year['close'].iloc[-1]
                if bm_prev_close is None:
                    start_price = bm_year['open'].iloc[0]
                else:
                    start_price = bm_prev_close
                    
                bm_ret = (end_price / start_price - 1) * 100
                bm_prev_close = end_price
        
        diff = port_ret - bm_ret
        annual_results.append({
            "연도": f"{y}년",
            "시스템수익률": port_ret,
            "KODEX200수익률": bm_ret,
            "초과수익(a)": diff
        })
        prev_val = end_val
        
    # 최종 누적 계산
    total_port_ret = ((df_hist['total_value'].iloc[-1] / port_res['initial_capital']) - 1) * 100
    total_bm_ret = 0.0
    if bm_df is not None and not bm_df.empty:
        total_bm_ret = ((bm_df['close'].iloc[-1] / bm_df['open'].iloc[0]) - 1) * 100
    total_diff = total_port_ret - total_bm_ret
    
    annual_results.append({
        "연도": "전체(5년 누적)",
        "시스템수익률": total_port_ret,
        "KODEX200수익률": total_bm_ret,
        "초과수익(a)": total_diff
    })
        
    print("REPORT_START")
    md = "| 연도 (Year) | IRP 스크리너 수익률 (100% 폭격) | KOSPI 200 수익률 (B&H) | 초과 수익률 (Alpha) |\n"
    md += "|---|---|---|---|\n"
    for idx, r in enumerate(annual_results):
        emoji = "🔥 시장 압도" if r["초과수익(a)"] > 0 else "🌧️ 방어 위주"
        if r["연도"] == "전체(5년 누적)":
            md += f"| **{r['연도']}** | **{r['시스템수익률']:+,.2f}%** | **{r['KODEX200수익률']:+,.2f}%** | **{r['초과수익(a)']:+,.2f}%** ({emoji}) |\n"
        else:
            md += f"| {r['연도']} | {r['시스템수익률']:+,.2f}% | {r['KODEX200수익률']:+,.2f}% | **{r['초과수익(a)']:+,.2f}%** ({emoji}) |\n"
        
    md += "\n> **※ 분석 업데이트:** 회원님의 지적에 따라, 30% 현금 안전보유 착시를 제거하고 **'투입된 위험자산 70%' 시드머니 한도 자체를 100%로 치환하여 타겟 3종목에 33.3%씩 전액 폭격**했을 때의 100% 투명한 코어 퍼포먼스입니다.\n"
    print(md)
    print("REPORT_END")

if __name__ == "__main__":
    run_annual_report()
