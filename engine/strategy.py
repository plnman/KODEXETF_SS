import pandas as pd

# 사용자 오버라이드 가능한 기본 세팅
DEFAULT_K_BASE = 0.5
ATR_MULTIPLIER = 1.6
TRAILING_STOP_PERCENT = 0.10  # 고점 대비 10% 하락 시 익절
RSI_OVERSOLD_THRESHOLD = 20
ADX_TREND_THRESHOLD = 20

def calculate_dynamic_k(sigma_20: float, sigma_avg: float, k_base: float = DEFAULT_K_BASE) -> float:
    """
    [동적 K-Value]
    최근 20일 변동성(sigma_20)이 연평균 대비 높으면 진입 장벽(K)을 올리고,
    변동성이 낮으면 진입 장벽을 낮춰 잦은 손절을 막고 돌파 가치를 극대화시킵니다.
    """
    if pd.isna(sigma_avg) or sigma_avg == 0:
        return k_base
    if pd.isna(sigma_20):
        return k_base
        
    k_adj = k_base * (sigma_20 / sigma_avg)
    # 극단적인 K값 폭주 방지(Clipping: 시장이 비정상일 때 시스템 보호)
    return max(0.2, min(k_adj, 0.8))

def build_signals_and_targets(df: pd.DataFrame, ticker_k_base: float = DEFAULT_K_BASE) -> pd.DataFrame:
    """
    Lookahead Bias (타임머신 오류) 원천 차단을 최우선시 한 매매 시그널 벡터 생성 코어.
    T일의 '종가(Close)'가 완전히 확정된 후의 지표만을 사용하여,
    무조건 다음날(T+1) 시가(Open) 또는 T+1 장중 돌파 가격에 매매되도록 강제 Shift합니다.
    """
    
    # 1. 횡적 변동성 분석 및 동적 K 반영
    df['k_adj'] = df.apply(
        lambda row: calculate_dynamic_k(row['sigma_20'], row['sigma_avg'], ticker_k_base), 
        axis=1
    )
    
    # 전일(T-1) 레인지를 기반으로 한 T일 장중 돌파 타겟 설정
    df['range'] = df['high'] - df['low']
    df['prev_range'] = df['range'].shift(1)
    df['target_break_price'] = df['open'] + (df['prev_range'] * df['k_adj'])
    
    # 2. 보조지표 필터 (T일 기준 결산 확인용)
    cond_adx = df['adx_14'] >= ADX_TREND_THRESHOLD
    cond_rsi = df['rsi_2'] <= RSI_OVERSOLD_THRESHOLD
    
    # 3. L3 CVD 가짜 양봉 룰 검사
    # cvd_score가 DB 데이터 조인을 통해 탑재되었다고 가정합니다.
    if 'cvd_score' in df.columns:
        # 종가 > 시가 이면서 cvd_score가 음수(마이너스)면 외화내빈(가짜 상승)으로 판정
        cond_cvd_fake_bull = (df['close'] > df['open']) & (df['cvd_score'] < 0)
        cond_cvd_valid = ~cond_cvd_fake_bull
    else:
        # 단기 지표 테스트를 위한 Fallback 스위치
        cond_cvd_valid = True

    # 4. T+1 시점의 시가 매수 여부 결정 (오류 제거를 위한 Shift 연산)
    # 필터들을 모두 통과한 날 = T
    df['buy_signal_T'] = cond_adx & cond_rsi & cond_cvd_valid
    
    # "T+1 시점 시가 매수" = execute_buy_T_plus_1
    df['execute_buy_T_plus_1'] = df['buy_signal_T'].shift(1)
    
    # 5. 방어선 (Hard Stop) 퍼센테이지 (T+1일 시가 대비 ATR 기반 낙하 폭)
    df['hard_stop_loss_pct'] = (df['atr_14'].shift(1) * ATR_MULTIPLIER) / df['close'].shift(1)
    
    return df
