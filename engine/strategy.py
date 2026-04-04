import pandas as pd
import numpy as np

# -------------------------------------------------------------------------------------
# [V3.1.2 INTEGRITY ENGINE] EMERGENCY RECOVERY SYNC (2026-04-01 16:40) 🕋🚀
# -------------------------------------------------------------------------------------
TICKER_PARAMS = {
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
    # [NEW] 글로벌 / 메가트렌드 편입 (V3.5.0)
    "KODEX 미국S&P500TR": {'k': 0.7, 'mfi': 40, 'adx_threshold': 15},
    "KODEX 미국나스닥100TR": {'k': 0.5, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 미국FANG플러스(H)": {'k': 0.4, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 미국산업재(합성)": {'k': 0.5, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 선진국MSCI World": {'k': 0.6, 'mfi': 40, 'adx_threshold': 15},
    "KODEX 글로벌AI인프라": {'k': 0.3, 'mfi': 55, 'adx_threshold': 20},
    "KODEX 인도Nifty50": {'k': 0.6, 'mfi': 50, 'adx_threshold': 15},
    "KODEX 미국반도체MV": {'k': 0.3, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 미국배당프리미엄액티브": {'k': 0.8, 'mfi': 40, 'adx_threshold': 15},
    "KODEX K방산TOP10": {'k': 0.3, 'mfi': 60, 'adx_threshold': 20},
    "KODEX 바이오": {'k': 0.2, 'mfi': 60, 'adx_threshold': 15},
    "KODEX Top5PlusTR": {'k': 0.5, 'mfi': 50, 'adx_threshold': 15},
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

def get_market_regime(market_df: pd.DataFrame, use_global_mfi: bool = True) -> pd.Series:
    """
    [V3.1] 시장(K200)의 ADX Z-Score를 기반으로 레짐(Bull/Stable)을 판독합니다.
    """
    df = market_df.copy()
    window = 252
    adx_mean = df['adx_14'].rolling(window=window).mean()
    adx_std = df['adx_14'].rolling(window=window).std()
    z_score = (df['adx_14'] - adx_mean) / adx_std
    
    # 히스테리시스 적용 (Bull: Z-Score 2.0 이상 & MFI 40 이상 진입, 1.0 미만 시 퇴거)
    regime = []
    curr = False
    for i, z in enumerate(z_score):
        if pd.isna(z): 
            regime.append(False)
            continue
        # [V3.4.0 Global MFI Filter] 시장 전체 유동성(MFI) 40 이상 허가
        mfi_ok = True
        if use_global_mfi and 'mfi' in df.columns: mfi_ok = df['mfi'].iloc[i] > 40
        
        if not curr and z > 2.0 and mfi_ok: curr = True
        elif curr and (z < 1.0): curr = False
        regime.append(curr)
    return pd.Series(regime, index=df.index)

def build_signals_and_targets(df: pd.DataFrame, ticker_name: str = "DEFAULT", overrides: dict = None, is_bull_market = False, turbo_discount: float = 0.5) -> pd.DataFrame:
    """
    [V3.1 지능형 하이브리드 엔진]
    is_bull_market: 실전 매매 시에는 현재 레짐(bool), 백테스트 시에는 날짜별 레짐(Series)을 입력받습니다.
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
    df['sma_10'] = df['close'].rolling(window=10).mean()
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_60'] = df['close'].rolling(window=60).mean()
    df['sma_120'] = df['close'].rolling(window=120).mean()
    df['rs_20'] = df['close'].pct_change(periods=20)
    
    # [V3.1.2] Composite RS (복합 주도주 지수) 산출
    # 단순 20일 수익률에 추세 가중치 부여: 역배열 종목(넌센스)을 순위에서 강제 퇴출
    is_above_20 = df['close'] > df['sma_20']
    is_above_60 = df['close'] > df['sma_60']
    is_above_120 = df['close'] > df['sma_120']
    
    # 정배열 점수 (3단계 가점)
    trend_score = is_above_20.astype(int) + is_above_60.astype(int) + is_above_120.astype(int)
    
    # Composite RS = rs_20 * (1 + 0.5 * trend_score)
    # 추세가 무너진 종목(trend_score=0)은 수익률이 좋아도 점수가 낮게 유지됨
    df['composite_rs'] = df['rs_20'] * (1.0 + 0.5 * trend_score)
    
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
    # 3. 타겟 브레이크 프라이스 (목표가) 계산 및 [V3.1] 불장 가속기 적용
    # ----------------------------------------------------
    k_orig = df.apply(
        lambda row: calculate_dynamic_k(row['sigma_20'], row['sigma_avg'], k_base_val), 
        axis=1
    )
    # 불장 판독용 벡터 정렬 (Index Alignment)
    if isinstance(is_bull_market, pd.Series):
        is_bull_v = is_bull_market.reindex(df.index).fillna(False).values
    else:
        is_bull_v = is_bull_market

    # [V3.4.0 Turbo-K] 불장일 경우 변동성 돌파 기준(K)을 낮춰서 진입
    df['is_bull_market'] = is_bull_v
    df['k_adj'] = np.where(is_bull_v, k_orig * turbo_discount, k_orig)
    
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
    
    # [V3.1] 종목별 다이내믹 엑시트 (Dynamic Exit Lookback)
    # 1. 과열 불장(is_bull_market) 시에는 전 종목 10일선으로 바짝 추격 익절
    # 2. 일반 장세에서는 종목별 변동성(ATR/Price)에 따라 10~20일선 자동 조절
    df['rel_vol'] = df['atr_14'] / df['close']
    df['vol_rank'] = df['rel_vol'].rolling(window=252).rank(pct=True) # 자기 변동성 대비 현재 수준 (0.0~1.0)
    
    # [V3.5.2 Intelligent Exit Engine]
    # 1. 초강력 불장(is_bull_market) 시에는 5일선 이격 매도로 익절을 극대화
    # 2. 일반 장세에서는 변동성(ATR)에 따라 10~20일선 자동 추전
    df['exit_signal_T'] = np.where(
        is_bull_v, 
        df['close'] < df['sma_5'], 
        np.where(df['vol_rank'] < 0.3, df['close'] < df['sma_10'], df['close'] < df['sma_20'])
    )
    
    # IRP T+1 실행 확정 변수
    df['execute_buy_T_plus_1'] = df['buy_signal_T'].shift(1)
    df['execute_exit_T_plus_1'] = df['exit_signal_T'].shift(1)
    
    df['hard_stop_loss_pct'] = (df['atr_14'].shift(1) * ATR_MULTIPLIER) / df['close'].shift(1)
    
    return df
