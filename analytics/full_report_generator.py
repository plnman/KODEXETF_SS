import yfinance as yf
import pandas as pd
import sys
from engine.strategy import build_signals_and_targets
from analytics.backtester import run_vectorized_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS
import warnings
warnings.filterwarnings('ignore')

def run_full_report():
    # 윈도우 한글 깨짐 방지용 내부 인코딩 강제 설정
    sys.stdout.reconfigure(encoding='utf-8')
    
    results = []
    total_initial_capital = 50000000.0  # 총 원금 5천만원
    capital_per_ticker = total_initial_capital / len(TARGET_ETFS) # 종목당 500만원씩 병렬 독립 배분
    
    total_final_capital = 0.0
    
    tickers_list = list(TARGET_ETFS.keys())
    # 2019년부터 과거 5년 풀 데이터 수집
    data = yf.download(tickers_list, start="2019-01-01", end="2026-12-31", progress=False)
    
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, raw_ticker) in data.columns:
                df_clean[col.lower()] = data[(col, raw_ticker)]
            elif col in data.columns and len(tickers_list) == 1:
                df_clean[col.lower()] = data[col]
                
        df_clean = df_clean.dropna().reset_index()
        df_clean['date'] = df_clean['Date'].dt.strftime('%Y-%m-%d')
        
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        df_clean = df_clean.dropna().reset_index(drop=True)
        
        # 10대 섹터 대상 일봉 기반 시그널 발사 (Dynamic K=0.5)
        signals = build_signals_and_targets(df_clean, ticker_k_base=0.5)
        # 종점 도달 후 슬리피지 0% T+1 백테스트 진행
        backtest_res = run_vectorized_backtest(signals, initial_capital=capital_per_ticker)
        
        if "error" not in backtest_res:
            profit_amount = backtest_res['final_capital'] - capital_per_ticker
            return_rate = (profit_amount / capital_per_ticker) * 100
            
            results.append({
                "종목명": name,
                "적용파라미터": "K=0.5, MFI>60, II>0",
                "거래횟수": backtest_res['total_trades'],
                "수익률": return_rate,
                "수익금액": profit_amount,
                "최종잔고": backtest_res['final_capital']
            })
            total_final_capital += backtest_res['final_capital']
        else:
            total_final_capital += capital_per_ticker

    total_profit = total_final_capital - total_initial_capital
    total_return_rate = (total_profit / total_initial_capital) * 100
    
    print("REPORT_START")
    md = "| 종목명 (Ticker) | 기본 파라미터 | 5년 거래 횟수 | 5년 누적 수익률 | 누적 수익금액 | 최종 잔고 |\n"
    md += "|---|---|---|---|---|---|\n"
    for r in results:
        md += f"| {r['종목명']} | {r['적용파라미터']} | {r['거래횟수']}회 | {r['수익률']:,.2f}% | {r['수익금액']:,.0f}원 | {r['최종잔고']:,.0f}원 |\n"
        
    md += "\n### 📈 KODEX IRP 10대 우량 섹터 병렬 배치 (5년 시뮬레이션 총합)\n"
    md += f"- **초기 투입 원금 총합:** {total_initial_capital:,.0f} 원\n"
    md += f"- **실전 매매 최종 잔고:** {total_final_capital:,.0f} 원\n"
    md += f"- **전종목 합산 수익금액:** {total_profit:,.0f} 원\n"
    md += f"- **전종목 합산 수익률 (Total Return):** {total_return_rate:,.2f} %\n"
    md += "\n*(이 결과는 '매주 상위 3개 주도주 몰빵(섹터 로테이션)' 로직이 들어가기 전, 단순히 10개 모든 종목에 500만 원씩 묵묵히 독립적으로 배분하여 매매한 방어적 베이스라인 성과입니다!)*\n"
    print(md)
    print("REPORT_END")

if __name__ == "__main__":
    run_full_report()
