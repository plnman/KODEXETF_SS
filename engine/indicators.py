import pandas as pd
import pandas_ta as ta

def calculate_rsi2(df: pd.DataFrame, close_col="close"):
    """
    RSI-2 (2일): 14일 RSI의 둔감함을 해결하여 극단적 단기 과매도 구간 포착
    """
    df['rsi_2'] = ta.rsi(df[close_col], length=2)
    return df

def calculate_atr(df: pd.DataFrame, high_col="high", low_col="low", close_col="close", length=14):
    """
    ATR (14일): 종목별 변동성 진폭을 수용하는 객관적 HardStop 기준선
    """
    df['atr_14'] = ta.atr(df[high_col], df[low_col], df[close_col], length=length)
    return df

def calculate_adx(df: pd.DataFrame, high_col="high", low_col="low", close_col="close", length=14):
    """
    ADX (14일): 횡보장에서의 잦은 손절을 방지하는 수문장 (L2 추세 필터, 20+ 구간 통과)
    """
    adx_df = ta.adx(df[high_col], df[low_col], df[close_col], length=length)
    if adx_df is not None:
        df['adx_14'] = adx_df[f'ADX_{length}']
    else:
        df['adx_14'] = 0.0
    return df

def calculate_sma20_divergence(df: pd.DataFrame, close_col="close"):
    """
    이격도 SMA20: 표준편차 모호함을 제거하고 고정 이격도로 타점 통제
    """
    df['sma_20'] = ta.sma(df[close_col], length=20)
    df['divergence_20'] = (df[close_col] / df['sma_20']) * 100
    return df

def calculate_recent_volatility(df: pd.DataFrame, close_col="close", length=20):
    """
    최근 20일 변동성 (표준편차)
    동적 K값을 계산하기 위해 시장 변동성 측정 (사용자 요구사항 대응)
    """
    df['sigma_20'] = df[close_col].rolling(window=length).std()
    # 1년(252일) 이동 평균 표준편차를 sigma_avg로 사용하여 현재 분위 파악
    df['sigma_avg'] = df['sigma_20'].rolling(window=252, min_periods=20).mean() 
    return df

def apply_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """모든 보조지표를 벡터라이징 방식으로 일괄 계산 (성능 최적화)"""
    df = calculate_rsi2(df)
    df = calculate_atr(df)
    df = calculate_adx(df)
    df = calculate_sma20_divergence(df)
    df = calculate_recent_volatility(df)
    # 결측치 정제
    df.fillna(method='bfill', inplace=True)
    return df
