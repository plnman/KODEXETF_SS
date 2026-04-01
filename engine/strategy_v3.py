import pandas as pd
import numpy as np

# -------------------------------------------------------------------------------------
# [FINAL SPEC] KODEX IRP 무결성 매매 엔진 전용: 종목별 팩터 매핑 딕셔너리 (Parameter Profiling)
# 종목 고유의 변동성(Beta)과 주포의 핸들링 특성을 반영하여 개별 최적화된 파라미터입니다.
# -------------------------------------------------------------------------------------
TICKER_PARAMS = {
    "KODEX 200": {'k': 0.6, "mfi": 50, "adx_threshold": 15},
    "KODEX 코스닥150": {'k': 0.2, "mfi": 50, "adx_threshold": 15},
    "KODEX 반도체": {'k': 0.2, "mfi": 50, "adx_threshold": 15},
    "KODEX 은행": {'k': 0.6, "mfi": 65, "adx_threshold": 20},
    "KODEX 자동차": {'k': 0.2, "mfi": 50, "adx_threshold": 15},
    "KODEX 2차전지산업": {'k': 0.3, "mfi": 60, "adx_threshold": 15},
    "KODEX 건설": {'k': 0.3, "mfi": 60, "adx_threshold": 15},
    "KODEX 금융": {'k': 0.5, "mfi": 65, "adx_threshold": 20},
    "KODEX 기계장비": {'k': 0.2, "mfi": 40, "adx_threshold": 15},
    "KODEX 철강": {'k': 0.6, "mfi": 40, "adx_threshold": 15},
}

# 공통 하드 스탑 방벽 (과도한 5일선 칼손절 방지를 위해 3.0 유지)
ATR_MULTIPLIER = 3.0 

def calculate_dynamic_k(sigma_20: float, sigma_avg: float, k_base: float) -> float:
    if pd.isna(sigma_avg) or sigma_avg == 0:
        return k_base
    if pd.isna(sigma_20):
        return k_base
    k_adj = k_base * (sigma_20 / sigma_avg)
    return max(0.2, min(k_adj, 0.8))

def build_signals_and_targets(df: pd.DataFrame, ticker_name: str = "DEFAULT", overrides: dict = None) -> pd.DataFrame:
    """
    [IRP 전용 무결성 매매 시그널 벡터 생성 엔진 (Daily-Only)]
    ADX 14 필터를 추가하여 횡보장(Box-pi) Whipsaw 갈갈이 장세를 원천 차단하고, 
    각 종목 고유의 특성 사전(TICKER_PARAMS)을 로드하여 완전히 독립적인 변동성 돌파를 집도합니다.
    """
    df = df.sort_values('date').copy()
    
    # 종목별 맞춤 파라미터 로드 (오버라이드가 들어오면 덮어씌움)
    params = TICKER_PARAMS.get(ticker_name, {"k": 0.5, "mfi": 60, "adx_threshold": 20})
    if overrides:
        params.update(overrides)
        
    k_base_val = params["k"]
    mfi_val = params["mfi"]
    adx_val = params["adx_threshold"]
    
    df['sigma_20'] = df['close'].rolling(window=20).std()
    df['sigma_avg'] = df['sigma_20'].rolling(window=252, min_periods=20).mean()
    df['sma_5'] = df['close'].rolling(window=5).mean()
    df['sma_10'] = df['close'].rolling(window=10).mean() # [V3] 가속/고점 익절선
    df['sma_20'] = df['close'].rolling(window=20).mean() # 중기 추세방어선 (익절/손절 하한선)
    df['rs_20'] = df['close'].pct_change(periods=20)
    
    # ----------------------------------------------------
    # 1. 고전적 변동성/방어선 지표 연산 (ATR)
    # ----------------------------------------------------
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_14'] = tr.ewm(alpha=1/14, min_periods=14).mean()
    
    # ----------------------------------------------------
    # 2. ADX 14 (추세 강도 필터: Market Regime Filter)
    # 지루한 박스권 횡보장에서 상하단 가짜 돌파에 당하는 것을 철벽 방어!
    # ----------------------------------------------------
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    
    safe_atr = np.where(df['atr_14'] == 0, 0.0001, df['atr_14'])
    df['plus_di'] = 100 * (df['plus_dm'].ewm(alpha=1/14, min_periods=14).mean() / safe_atr)
    df['minus_di'] = 100 * (df['minus_dm'].ewm(alpha=1/14, min_periods=14).mean() / safe_atr)
    
    di_sum = df['plus_di'] + df['minus_di']
    safe_di_sum = np.where(di_sum == 0, 0.0001, di_sum)
    df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / safe_di_sum
    df['adx_14'] = df['dx'].ewm(alpha=1/14, min_periods=14).mean()
    
    # ----------------------------------------------------
    # 3. 타겟 브레이크 프라이스 (목표가) 계산
    # ----------------------------------------------------
    df['k_orig'] = df.apply(
        lambda row: calculate_dynamic_k(row['sigma_20'], row['sigma_avg'], k_base_val), 
        axis=1
    )
    # [V3] 강세장 가속 진입 필터 (ADX > 30일 때 K 20% 할인)
    df['k_adj'] = np.where(df['adx_14'] > 30, df['k_orig'] * 0.8, df['k_orig'])

    df['range'] = df['high'] - df['low']
    df['prev_range'] = df['range'].shift(1)
    df['target_break_price'] = df['open'] + (df['prev_range'] * df['k_adj'])
    
    # ----------------------------------------------------
    # 4. 진입 조건 (종목별 최적화된 파라미터로 철저히 판독!)
    # ----------------------------------------------------
    cond_price_break = df['close'] > df['target_break_price']
    cond_mfi = df['mfi'] > mfi_val  
    cond_ii = df['intraday_intensity'] > 0
    cond_adx = df['adx_14'] > adx_val # [NEW] 시장의 추세(Trend)가 살아있을 때만 진입 허가! 가짜 돌파 출입 금지.

    # 4가지 핵심 팩터(가격돌파, 스마트머니, 일봉지배력, 추세강도)를 100% 만족해야만 매수 시그널 발생!
    df['buy_signal_T'] = cond_price_break & cond_mfi & cond_ii & cond_adx
    
    # [V3] 가변적 청산 조건 (Dynamic Exit)
    # 추세 강도가 35 이상으로 과열 시 10일선으로 타이트하게 익절, 평상시 20일선 추종
    df['exit_signal_T'] = np.where(
        df['adx_14'] > 35, 
        df['close'] < df['sma_10'], 
        df['close'] < df['sma_20']
    )
    
    # IRP T+1 실행 확정 변수
    df['execute_buy_T_plus_1'] = df['buy_signal_T'].shift(1)
    df['execute_exit_T_plus_1'] = df['exit_signal_T'].shift(1)
    
    df['hard_stop_loss_pct'] = (df['atr_14'].shift(1) * ATR_MULTIPLIER) / df['close'].shift(1)
    
    return df
