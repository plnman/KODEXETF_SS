import pandas as pd
import numpy as np

def calculate_rsi2(df: pd.DataFrame, close_col="close"):
    """
    RSI-2 (2일): 14일 RSI의 둔감함을 해결하여 극단적 단기 과매도 구간 포착.
    (pandas-ta 의존성을 제거하고 Wilder's 리얼 수식으로 100% 자체 구현)
    """
    delta = df[close_col].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    
    roll_up = up.ewm(alpha=1/2, min_periods=2).mean()
    roll_down = down.abs().ewm(alpha=1/2, min_periods=2).mean()
    
    rs = roll_up / roll_down
    df['rsi_2'] = 100.0 - (100.0 / (1.0 + rs))
    df['rsi_2'] = df['rsi_2'].fillna(100)
    return df

def calculate_atr(df: pd.DataFrame, high_col="high", low_col="low", close_col="close", length=14):
    """
    ATR (14일): 종목별 변동성 진폭을 수용하는 객관적 HardStop 기준선.
    """
    high_low = df[high_col] - df[low_col]
    high_close = (df[high_col] - df[close_col].shift()).abs()
    low_close = (df[low_col] - df[close_col].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    
    df['atr_14'] = true_range.ewm(alpha=1/length, min_periods=length).mean()
    return df

def calculate_adx(df: pd.DataFrame, high_col="high", low_col="low", close_col="close", length=14):
    """
    ADX (14일): 횡보장에서의 잦은 손절을 방지하는 수문장 (L2 추세 필터).
    """
    up = df[high_col] - df[high_col].shift(1)
    down = df[low_col].shift(1) - df[low_col]
    
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    
    high_low = df[high_col] - df[low_col]
    high_close = (df[high_col] - df[close_col].shift()).abs()
    low_close = (df[low_col] - df[close_col].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    atr = tr.ewm(alpha=1/length, min_periods=length).mean()
    
    plus_di = 100 * (plus_dm.ewm(alpha=1/length, min_periods=length).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/length, min_periods=length).mean() / atr)
    
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    df['adx_14'] = dx.ewm(alpha=1/length, min_periods=length).mean()
    df['adx_14'] = df['adx_14'].fillna(0.0)
    return df

def calculate_sma20_divergence(df: pd.DataFrame, close_col="close"):
    """
    이격도 SMA20: 표준편차 모호함을 제거하고 고정 이격도로 타점 통제.
    """
    df['sma_20'] = df[close_col].rolling(window=20).mean()
    df['divergence_20'] = (df[close_col] / df['sma_20']) * 100
    return df

def calculate_recent_volatility(df: pd.DataFrame, close_col="close", length=20):
    """
    최근 20일 변동성 (표준편차): K값을 시장 분위기에 맞게 동적 컨트롤용.
    """
    df['sigma_20'] = df[close_col].rolling(window=length).std()
    df['sigma_avg'] = df['sigma_20'].rolling(window=252, min_periods=20).mean() 
    return df

def apply_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """모든 보조지표를 벡터라이징 방식으로 일괄 계산 (의존성 없음)"""
    df = calculate_rsi2(df)
    df = calculate_atr(df)
    df = calculate_adx(df)
    df = calculate_sma20_divergence(df)
    df = calculate_recent_volatility(df)
    # 룩어헤드를 제거하기 위해 ffill 먼저 한 뒤 맨 앞의 결측치만 bfill
    df = df.ffill().bfill()
    return df
