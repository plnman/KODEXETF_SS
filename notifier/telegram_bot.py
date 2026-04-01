import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import sys

# 코어 엔진 폴더를 참조하기 위해 path 삽입
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS
from engine.screener import get_top_sectors_for_week

def send_telegram_message(message: str):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("Telegram Token이 .env 에 설정되지 않아 발송이 스킵되었습니다.")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print("✅ 텔레그램 수동 매매 지시서 발송 성공")
    except Exception as e:
        print(f"❌ 텔레그램 발송 실패: {e}")

def scrape_and_notify():
    load_dotenv()
    print("수동 매매 텔레그램 시그널 봇 구동 중...")
    
    tickers_list = list(TARGET_ETFS.keys())
    data = yf.download(tickers_list, start="2023-01-01", progress=False) 
    
    all_signals = {}
    for raw_ticker, name in TARGET_ETFS.items():
        df_clean = pd.DataFrame()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if (col, raw_ticker) in data.columns:
                df_clean[col.lower()] = data[(col, raw_ticker)]
            elif col in data.columns and len(tickers_list) == 1:
                df_clean[col.lower()] = data[col]
        if df_clean.empty: continue
            
        df_clean = df_clean.dropna().reset_index()
        df_clean['date'] = df_clean['Date'].dt.strftime('%Y-%m-%d')
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        df_clean = df_clean.dropna().reset_index(drop=True)
        all_signals[name] = build_signals_and_targets(df_clean, ticker_name=name)

    today_date = max(df['date'].max() for df in all_signals.values())
    top_3_with_scores = get_top_sectors_for_week(all_signals, today_date)
    top_3_names = [x[0] for x in top_3_with_scores]
    
    msg_lines = [
        "<b>🔥 [KODEX IRP 매매 시그널 브리핑]</b>\n",
        f"📅 데이터 스크랩 기준일: {today_date}\n",
        f"🏆 <b>금주 실전 주도 섹터 (Top 3):</b>",
        f"1위. {top_3_with_scores[0][0]} (수익률 방어 기반 RS: {top_3_with_scores[0][1]*100:.1f}%)",
        f"2위. {top_3_with_scores[1][0]} (수익률 방어 기반 RS: {top_3_with_scores[1][1]*100:.1f}%)",
        f"3위. {top_3_with_scores[2][0]} (수익률 방어 기반 RS: {top_3_with_scores[2][1]*100:.1f}%)\n"
    ]
    
    buy_signals = []
    sell_signals = []
    
    for name, df in all_signals.items():
        if df.empty: continue
        last_row = df.iloc[-1]
        if last_row['date'] != today_date: continue
        
        if name in top_3_names and last_row['buy_signal_T']:
            buy_signals.append(f"🟢 <b>[매수 지시] {name}</b>\n - <ins>사유:</ins> 돌파 타점/수급(MFI: {last_row['mfi']:.1f}) 통과 및 횡보장 회피 검증(ADX: {last_row['adx_14']:.1f})\n - <ins>명일 시가 전, 현금 비중 33% 이내 분할 매수 추천</ins>")
            
        # 20일선 이탈(대추세 붕괴) 청산 시그널
        if last_row['exit_signal_T']:
            sell_signals.append(f"🔴 <b>[청산 지시] {name}</b>\n - <ins>사유:</ins> 중기 20일 추세선 하회 이탈 (대세 상승 동력 소멸)\n - <ins>보유 물량 명일 시가 개장 전 전량 매도 추천</ins>")
            
    if buy_signals:
        msg_lines.append("\n📈 <b>[신규 진입 브리핑]</b>")
        msg_lines.extend(buy_signals)
    if sell_signals:
        msg_lines.append("\n📉 <b>[기존 포지션 전량 청산 브리핑]</b>")
        msg_lines.extend(sell_signals)
        
    if not buy_signals and not sell_signals:
        msg_lines.append("\n✅ 오늘은 신규로 진입하거나 매도할 타점이 전혀 없습니다. 시드 머니와 주식을 그대로 보유(관망)합니다.")
        
    msg_lines.append("\n👉 <i>자세한 통계 지표는 개인 UI 웹 대시보드에서 체크하세요.</i>")
    send_telegram_message("\n".join(msg_lines))

if __name__ == "__main__":
    scrape_and_notify()
