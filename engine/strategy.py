import pandas as pd
import numpy as np

from config.etf_universe import TICKER_PARAMS  # noqa: F401 — Single Source of Truth (config/etf_universe.py)

# 공통 하드 스탑 방벽 (V3.6.0 최적화 결과 2.5 채택 — MDD -30.9%→-24.5%, 수익 +109%p)
ATR_MULTIPLIER = 2.5

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
    # [V3.8.2] NaN 중립 처리: 데이터 부족(신규 상장 ETF)으로 SMA가 NaN인 구간은
    #          False(패널티) 대신 0.5(중립)으로 처리 → 기존 ETF와 동등한 RS 경쟁 가능
    is_above_20  = df['close'] > df['sma_20']
    is_above_60  = df['close'] > df['sma_60']
    is_above_120 = df['close'] > df['sma_120']

    score_20  = is_above_20.astype(float)
    score_60  = is_above_60.where(df['sma_60'].notna(),  0.5).astype(float)
    score_120 = is_above_120.where(df['sma_120'].notna(), 0.5).astype(float)

    # 정배열 점수 (3단계 가점, NaN 구간은 0.5 중립)
    trend_score = score_20 + score_60 + score_120
    
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
