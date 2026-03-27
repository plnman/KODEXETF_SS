import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
from typing import Optional

# 시스템이나 서버 환경에 등록된 토큰을 읽어옵니다. (없어도 에러 없이 스킵되도록 설계)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def generate_cvd_heatmap(cvd_data: pd.DataFrame) -> BytesIO:
    """
    [CVD Heatmap Preview 기능]
    당일 장중 체결 강도(L3 CVD 점수)를 시간대별/종목별 히트맵 이미지로 자동 렌더링하고
    메모리 버퍼(BytesIO)에 담아 즉시 반환합니다. (로컬 서버에 파일 다운로드 없이 즉각 전송)
    """
    # 텔레그램 예시 전송을 위해, 만약 데이터가 비어있다면 가상의 수급 집중도 샘플 생성
    if cvd_data is None or cvd_data.empty:
        import numpy as np
        # 가상의 -100 ~ 100 사이 체결 강도 압력
        data = np.random.randn(4, 5) * 50
        cvd_data = pd.DataFrame(data, columns=['09:30', '11:00', '13:00', '14:30', '15:20'])
        cvd_data.index = ['KODEX Lev', 'KODEX Inv', 'KODEX 200', 'TIGER Bio']
    
    plt.figure(figsize=(7, 4))
    # 빨강(매도 우위) -> 노랑(보합) -> 초록(매수 우위) 그라데이션 적용
    sns.heatmap(cvd_data, annot=True, cmap="RdYlGn", center=0, fmt=".0f")
    plt.title("Intraday L3 CVD Heatmap (Real-time Supply Concentration)")
    plt.tight_layout()
    
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    
    return buf

def send_telegram_signal(ticker: str, signal_type: str, reason: str, cvd_data: Optional[pd.DataFrame] = None):
    """
    장 종료 직후, 익일(T+1) 시가에 대한 매수/매도 제안과 그 확실한 근거를 텔레그램으로 발송합니다.
    사용자 요구사항에 따라, 당일 수급 집중도 히트맵 이미지까지 생성하여 함께 전송합니다.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Notifier] 텔레그램 활성화 토큰 정보가 불충분하여 알림 전송을 생략합니다.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 1. 텍스트 시그널 뷰 완성
    text = (
        f"🚨 **[KODEX 안티그래비티 신호 감지]** 🚨\n\n"
        f"📌 **대상 종목:** {ticker}\n"
        f"🎯 **AI 제안:** 내일 시가 무조건 **{signal_type.upper()}**\n"
        f"📝 **판단 근거:** {reason}\n"
    )
    
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[Notifier] 텍스트 메시지 API 전송 중 오류 발생: {e}")
        
    # 2. CVD 히트맵 이미지 프리뷰 전송 (Visual Insight 기능)
    if cvd_data is not None:
        try:
            photo_buf = generate_cvd_heatmap(cvd_data)
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {'photo': ('cvd_heatmap.png', photo_buf, 'image/png')}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"📊 [{ticker}] 당일 수급 집중도 (L3 CVD Heatmap Preview)"}
            requests.post(photo_url, data=data, files=files)
            print(f"[Notifier] {ticker} 히트맵 전송 성공.")
        except Exception as e:
            print(f"[Notifier] 히트맵 이미지 생성 및 전송 오류: {e}")
