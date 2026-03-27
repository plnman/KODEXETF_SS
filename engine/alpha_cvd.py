import pandas as pd

def calculate_l3_cvd(intraday_df: pd.DataFrame) -> float:
    """
    1분봉 데이터 기반 L3 CVD (Cumulative Volume Delta) 엔진.
    당일 1분봉 데이터를 입력받아 분 단위 체결 강도를 누적 연산합니다.
    (용량 최적화를 위해 이 계산된 스코어만 cvd_summary에 저장하고 1분봉은 폐기됨)
    """
    if intraday_df.empty:
        return 0.0
        
    cvd_score = 0.0
    for _, row in intraday_df.iterrows():
        # 분봉별 가격 변동폭으로 매수/매도 우위 압력을 배분
        price_diff = row['close'] - row['open']
        if price_diff > 0:
            # 양봉: 매수 수급 유입
            cvd_score += row['volume'] * (price_diff / row['open'])
        elif price_diff < 0:
            # 음봉: 매도 수급 이탈
            cvd_score -= row['volume'] * (abs(price_diff) / row['open'])
            
    return cvd_score

def check_fake_bull_candle(daily_close: float, daily_open: float, cvd_score: float) -> bool:
    """
    가짜 양봉(Fake Bull) 철저 필터링:
    일봉상 종가가 시가보다 높아 겉보기엔 양봉이지만, 
    L3 CVD 스코어가 음수(내부 매도 압력 우위)라면 가짜 양봉으로 규정하여 진입 차단.
    """
    is_bull_candle = daily_close > daily_open
    if is_bull_candle and cvd_score < 0:
        return True # 가짜 양봉 판정
    return False # 진짜 수급
