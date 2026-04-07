# KODEX IRP 실전 매매 컨트롤 타워 — 시스템 개발 사양서

**버전:** V3.5.13
**작성일:** 2026-04-07
**목적:** 본 문서만으로 시스템 전체를 재현 가능하도록 작성된 완전 사양서

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [기술 스택 및 아키텍처](#2-기술-스택-및-아키텍처)
3. [대상 종목 및 파라미터](#3-대상-종목-및-파라미터)
4. [데이터 수집 및 지표 계산](#4-데이터-수집-및-지표-계산)
5. [시장 레짐 판단 엔진](#5-시장-레짐-판단-엔진)
6. [매매 신호 생성 엔진](#6-매매-신호-생성-엔진)
7. [포트폴리오 백테스트 엔진](#7-포트폴리오-백테스트-엔진)
8. [데이터베이스 스키마](#8-데이터베이스-스키마)
9. [프론트엔드 UI 구성](#9-프론트엔드-ui-구성)
10. [배포 환경](#10-배포-환경)
11. [무결성 및 검증](#11-무결성-및-검증)
12. [봉인된 확정값](#12-봉인된-확정값)

---

## 1. 시스템 개요

### 1.1 목적

개인 IRP(Individual Retirement Pension) 계좌에서 KODEX ETF를 대상으로
**변동성 돌파 + 수급 + 추세 + 레짐** 4중 필터를 통해 일별 매매 신호를 생성하고,
7년 백테스트 결과 기반의 알고리즘 트레이딩 컨트롤 타워를 제공한다.

### 1.2 핵심 제약 조건

| 제약 | 내용 |
|------|------|
| 계좌 유형 | IRP (퇴직연금) |
| 거래 가능 상품 | KRX 상장 KODEX ETF 한정 |
| 매매 시간 | 장 마감 후 신호 확인 → 익일(T+1) 시가 체결 |
| 레버리지 | 불가 |
| 공매도 | 불가 |
| 최대 보유 종목 | 5종목 (설정 가능: 3/5/10) |

### 1.3 백테스트 확정 성과 (봉인값)

| 항목 | 값 |
|------|-----|
| 기간 | 2019-01-02 ~ 2026-04-04 (7년 2개월) |
| 초기 자본 | 50,000,000원 |
| 최종 자본 | 약 231,420,000원 |
| 누적 수익률 | **362.84%** (5종목 기준) |
| KOSPI200 동기간 | 107.53% |
| Alpha | **+255.31%p** |
| CAGR | 약 26% |
| MDD | 계산값 (DB 캐시 참조) |

---

## 2. 기술 스택 및 아키텍처

### 2.1 기술 스택

| 구분 | 기술 | 버전/비고 |
|------|------|-----------|
| 언어 | Python | 3.13 |
| 프론트엔드 | Streamlit | Cloud 배포 |
| 데이터베이스 | Supabase (PostgreSQL) | |
| 데이터 소스 | FinanceDataReader (FDR) | KRX API |
| 수치 연산 | pandas, numpy | |
| 배포 | Streamlit Community Cloud | GitHub 연동 자동배포 |

### 2.2 디렉토리 구조

```
KODEXETF_SS/
├── frontend/
│   └── app.py                    # 메인 Streamlit 앱 (전체 UI + 오케스트레이션)
├── engine/
│   └── strategy.py               # 신호 생성 + 레짐 판단 (핵심 알고리즘)
├── analytics/
│   ├── portfolio_backtester.py   # 다종목 포트폴리오 백테스터
│   ├── backtester.py             # 단일 종목 벡터 백테스터 (보조)
│   └── integrity_monitor.py     # 백테스트 무결성 감사 로그
├── data_collector/
│   ├── daily_scraper.py          # MFI/II 지표 계산 + Supabase 업로드
│   └── supabase_client.py        # Supabase 연결 클라이언트
├── schema/
│   ├── init_db.sql               # 기본 테이블 생성
│   ├── add_naver_tables.sql      # Naver 이중화 테이블
│   ├── add_backtest_cache_tables.sql  # 백테스트 캐시 테이블
│   └── create_live_trades_table.sql   # 실전 체결 추적 테이블
└── docs/
    └── SYSTEM_SPEC_V3.5.md       # 본 사양서
```

### 2.3 데이터 흐름

```
[FDR/KRX API]
     │
     ▼
[load_live_signals_only()]          ← 실전: 최근 500일
[load_and_process_data_v3_5_2()]    ← 백테스트: 2019-01-02~2026-04-04
     │
     ▼
[calculate_mfi() + calculate_intraday_intensity()]   ← OHLCV → MFI, II
     │
     ▼
[build_signals_and_targets()]       ← 종목별 신호 생성 (strategy.py)
     │
     ├──► [get_market_regime()]     ← KODEX200 ADX Z-Score → Bull/Stable
     │
     ▼
[run_portfolio_backtest()]          ← 포트폴리오 시뮬레이션
     │
     ▼
[Supabase DB 캐시]                  ← 백테스트 결과 영구 저장
     │
     ▼
[Streamlit UI]                      ← 4개 탭 대시보드
```

---

## 3. 대상 종목 및 파라미터

### 3.1 대상 ETF 목록 (22종목)

| 티커 | 종목명 | K값 | MFI 임계 | ADX 임계 |
|------|--------|-----|----------|----------|
| 069500 | KODEX 200 | 0.7 | 40 | 15 |
| 226490 | KODEX 코스닥150 | 0.2 | 50 | 15 |
| 091160 | KODEX 반도체 | 0.2 | 50 | 15 |
| 091170 | KODEX 은행 | 0.7 | 65 | 20 |
| 091180 | KODEX 자동차 | 0.2 | 50 | 15 |
| 305720 | KODEX 2차전지산업 | 0.3 | 60 | 20 |
| 117700 | KODEX 건설 | 0.4 | 60 | 15 |
| 091220 | KODEX 금융 | 0.5 | 60 | 20 |
| 102970 | KODEX 기계장비 | 0.7 | 65 | 15 |
| 117680 | KODEX 철강 | 0.3 | 40 | 15 |
| 379800 | KODEX 미국S&P500TR | 0.7 | 40 | 15 |
| 367380 | KODEX 미국나스닥100TR | 0.5 | 50 | 15 |
| 314250 | KODEX 미국FANG플러스(H) | 0.4 | 60 | 20 |
| 315270 | KODEX 미국산업재(합성) | 0.5 | 50 | 15 |
| 251350 | KODEX 선진국MSCI World | 0.6 | 40 | 15 |
| 475380 | KODEX 글로벌AI인프라 | 0.3 | 55 | 20 |
| 453850 | KODEX 인도Nifty50 | 0.6 | 50 | 15 |
| 465610 | KODEX 미국반도체MV | 0.3 | 60 | 20 |
| 461580 | KODEX 미국배당프리미엄액티브 | 0.8 | 40 | 15 |
| 0080G0 | KODEX K방산TOP10 | 0.3 | 60 | 20 |
| 244580 | KODEX 바이오 | 0.2 | 60 | 15 |
| 315930 | KODEX Top5PlusTR | 0.5 | 50 | 15 |

**파라미터 의미:**
- **K값 (변동성 상수):** 변동성 돌파 목표가 계산에 사용. 낮을수록 민감(조기 진입), 높을수록 보수적
- **MFI 임계:** 이 값 초과 시 스마트머니 유입 조건 충족
- **ADX 임계:** 이 값 초과 시 추세 강도 조건 충족

### 3.2 시스템 전역 상수

| 상수 | 값 | 의미 |
|------|-----|------|
| ATR_MULTIPLIER | 3.0 | 하드 스탑로스 ATR 배수 |
| TURBO_DISCOUNT (KODEX200) | 0.5 | 레짐 판단용 K 할인율 |
| TURBO_DISCOUNT (개별종목) | 0.4 | 개별종목 Bull 레짐 K 할인율 |
| MAX_TICKERS | 5 | 기본 최대 보유 종목수 (3/5/10 선택) |
| INITIAL_CAPITAL | 50,000,000원 | 백테스트 초기 자본 |
| CASH_SWEEP_BUFFER | 0.002 (0.2%) | 예수금 투자 시 수수료 버퍼 |
| LIVE_LOOKBACK_DAYS | 500일 | 실전 신호 데이터 로딩 범위 |
| BACKTEST_START | 2019-01-02 | 백테스트 시작일 (봉인) |
| BACKTEST_END | 2026-04-04 | 백테스트 종료일 (봉인) |
| TARGET_ROWS | 1,781행 | KODEX200 정합 거래일수 |

---

## 4. 데이터 수집 및 지표 계산

### 4.1 데이터 소스

| 구분 | 소스 | 방법 | 기간 |
|------|------|------|------|
| 실전 신호 | FDR → KRX | `fdr.DataReader(ticker, start)` | 최근 500일 |
| 백테스트 | FDR → KRX | `fdr.DataReader(ticker, start, end)` | 2019-01-02~2026-04-04 |
| KOSPI200 벤치마크 | FDR → KRX | `fdr.DataReader("069500", "2019-01-01")` | 2019~현재 |

**FDR 반환 컬럼:** Open, High, Low, Close, Volume, Change (6개)

### 4.2 데이터 전처리

```python
# 1. MultiIndex 컬럼 정규화
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# 2. 컬럼명 소문자 통일
df.columns = [c.lower() for c in df.columns]

# 3. date 컬럼 표준화
df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

# 4. 날짜 정렬
df = df.sort_values('date')

# 5. KODEX200 날짜 축으로 개별종목 reindex (날짜 동기화)
df_sync = df.set_index('date').reindex(k200.set_index('date').index)
           .reset_index().ffill().fillna(0)
df_sync = df_sync.drop_duplicates(subset=['date'])
```

### 4.3 MFI (Money Flow Index) 계산

**목적:** 스마트머니(기관/외국인) 유입 여부를 OHLCV로 간접 추정
**기간:** 14일 롤링

```
Typical Price (TP) = (High + Low + Close) / 3
Money Flow (MF)    = TP × Volume

Positive MF = MF  (TP가 전일 대비 상승한 날)
Negative MF = MF  (TP가 전일 대비 하락한 날)

Money Flow Ratio (MFR) = Σ(Positive MF, 14일) / Σ(Negative MF, 14일)

MFI = 100 - (100 / (1 + MFR))
```

**예외 처리:**
- Negative MF = 0일 때 → MFR = 1,000,000 (완전 매수 우위)
- 결측값 → 50으로 채움 (중립)

### 4.4 Intraday Intensity (II) 계산

**목적:** 당일 장중 매수세가 매도세를 지배하는지 판단

```
Range = High - Low  (0이면 0.001로 대체)
II = ((2×Close - High - Low) / Range) × Volume
```

**해석:**
- II > 0: 종가가 일중 상단에 위치 → 매수 지배
- II < 0: 종가가 일중 하단에 위치 → 매도 지배

---

## 5. 시장 레짐 판단 엔진

### 5.1 개요

KODEX 200(069500)의 ADX를 기반으로 시장 전체를 **BULL(공격)** 또는 **STABLE(안정)** 로 판단.
레짐은 모든 22개 종목의 K값(진입 민감도)과 청산선에 직접 영향.

### 5.2 입력

- KODEX 200 일봉 데이터 (OHLCV + MFI 계산 후)
- `use_global_mfi=True` (MFI 필터 활성화)

### 5.3 계산 로직

**STEP 1: ADX 14일선 계산 (Wilder's EWM 방식)**

```python
# True Range
TR = max(High-Low, |High-PrevClose|, |Low-PrevClose|)

# Directional Movement
+DM = High - PrevHigh  (if > |Low - PrevLow| and > 0, else 0)
-DM = PrevLow - Low    (if > |High - PrevHigh| and > 0, else 0)

# ATR (14일 EWM)
ATR_14 = TR.ewm(alpha=1/14, min_periods=14).mean()

# DI (Directional Indicator)
+DI_14 = 100 × (+DM.ewm(alpha=1/14).mean() / ATR_14)
-DI_14 = 100 × (-DM.ewm(alpha=1/14).mean() / ATR_14)

# DX → ADX
DX = 100 × |+DI_14 - -DI_14| / (+DI_14 + -DI_14)
ADX_14 = DX.ewm(alpha=1/14, min_periods=14).mean()
```

**STEP 2: Z-Score 정규화 (252 거래일 롤링)**

```
ADX_μ = ADX_14.rolling(252).mean()
ADX_σ = ADX_14.rolling(252).std()
Z = (ADX_14_현재 - ADX_μ) / ADX_σ
```

**STEP 3: 이중 필터 + 히스테리시스**

```python
# 상태 전이 (히스테리시스)
for each day:
    if is_STABLE and Z > 2.0 and MFI > 40:
        → BULL 진입
    elif is_BULL and Z < 1.0:
        → STABLE 복귀
```

| 조건 | 값 |
|------|-----|
| BULL 진입 (Z 임계) | > 2.0 (상위 2.3% 구간) |
| STABLE 복귀 (Z 임계) | < 1.0 |
| BULL 진입 (MFI 임계) | > 40 |

**워밍업 필요 기간:** ADX EWM(~28일) + Z-Score rolling(252일) = **최소 280 거래일** → 500일 로딩으로 보장

### 5.4 레짐별 매매 파라미터 차이

| 구분 | BULL | STABLE |
|------|------|--------|
| K값 | K_base × (σ₂₀/σ_avg) × **0.4** | K_base × (σ₂₀/σ_avg) |
| K 범위 | 클램프 [0.2, 0.8] | 클램프 [0.2, 0.8] |
| 청산선 | **SMA 5일** 이탈 | vol_rank < 0.3 → SMA 10일 / 그외 → SMA 20일 |

---

## 6. 매매 신호 생성 엔진

### 6.1 파생 지표 계산 순서

`build_signals_and_targets(df, ticker_name, overrides, is_bull_market, turbo_discount)` 함수:

```python
# 1. 변동성
sigma_20  = close.rolling(20).std()
sigma_avg = sigma_20.rolling(252, min_periods=20).mean()

# 2. 이동평균
sma_5   = close.rolling(5).mean()
sma_10  = close.rolling(10).mean()
sma_20  = close.rolling(20).mean()
sma_60  = close.rolling(60).mean()
sma_120 = close.rolling(120).mean()

# 3. 모멘텀
rs_20 = close.pct_change(periods=20)

# 4. Composite RS (주도주 복합 지수)
is_above_20  = close > sma_20   # 정배열 체크
is_above_60  = close > sma_60
is_above_120 = close > sma_120
trend_score  = is_above_20 + is_above_60 + is_above_120  # 0~3점
composite_rs = rs_20 × (1.0 + 0.5 × trend_score)
# 역배열 종목은 rs_20이 좋아도 composite_rs가 낮게 유지됨

# 5. ATR 14일 (Wilder's EWM)
TR     = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
atr_14 = TR.ewm(alpha=1/14, min_periods=14).mean()

# 6. ADX 14일 (STEP 1과 동일 공식)
adx_14 = ... (위 5.3 참조)

# 7. 변동성 순위
rel_vol  = atr_14 / close
vol_rank = rel_vol.rolling(252).rank(pct=True)  # 0.0~1.0
```

### 6.2 Dynamic K 계산

```python
def calculate_dynamic_k(sigma_20, sigma_avg, k_base):
    if sigma_avg == 0 or isnan:
        return k_base
    k_adj = k_base × (sigma_20 / sigma_avg)
    return clamp(k_adj, min=0.2, max=0.8)

# Bull 레짐 시 추가 Turbo 할인
k_final = dynamic_k × turbo_discount  (is_bull=True)
k_final = dynamic_k                   (is_bull=False)
```

### 6.3 목표 돌파가 (Target Break Price) 계산

**변동성 돌파 전략 (래리 윌리엄스 방식 변형)**

```
PrevRange = PrevHigh - PrevLow
TargetBreakPrice = Today_Open + PrevRange × K_final
```

당일 종가가 TargetBreakPrice를 돌파하면 매수 조건 1번 충족.

### 6.4 매수 신호 생성 (4중 필터)

**4가지 조건 100% 동시 충족 시에만 buy_signal_T = True**

| 번호 | 조건 | 의미 | 파라미터 |
|------|------|------|---------|
| ① | close > target_break_price | 가격 돌파 | K_final |
| ② | mfi > mfi_threshold | 스마트머니 유입 | 종목별 40~65 |
| ③ | intraday_intensity > 0 | 일봉 매수 지배 | 고정 (양수 여부) |
| ④ | adx_14 > adx_threshold | 추세 강도 존재 | 종목별 15~20 |

```python
buy_signal_T = cond1 AND cond2 AND cond3 AND cond4
```

### 6.5 T+1 실행 확정

IRP 규정상 당일 신호 → 익일 시가 체결

```python
execute_buy_T_plus_1  = buy_signal_T.shift(1)   # 전일 신호 → 금일 시가 매수
execute_exit_T_plus_1 = exit_signal_T.shift(1)  # 전일 신호 → 금일 시가 청산
```

### 6.6 청산 신호 생성

```python
# BULL 레짐: SMA 5일선 이탈 (빠른 익절)
exit_bull = close < sma_5

# STABLE 레짐 (변동성 기준 자동 선택)
exit_stable = (close < sma_10)  if vol_rank < 0.3  # 저변동성 종목
            | (close < sma_20)  if vol_rank >= 0.3 # 고변동성 종목

exit_signal_T = exit_bull (is_bull=True) | exit_stable (is_bull=False)
```

### 6.7 하드 스탑로스

```python
hard_stop_loss_pct = (atr_14.shift(1) × ATR_MULTIPLIER) / close.shift(1)
hard_stop_price    = entry_price × (1 - hard_stop_loss_pct)

# 장중 low가 hard_stop_price 이하 → 즉시 손절
if today_low <= hard_stop_price:
    exit_price = hard_stop_price
    reason = "Hard Stop (방어선 붕괴)"
```

**ATR_MULTIPLIER = 3.0** (고정)

---

## 7. 포트폴리오 백테스트 엔진

### 7.1 개요

`run_portfolio_backtest(all_signals_dict, initial_capital, max_tickers, use_cash_sweep)`

- 22개 종목 신호를 받아 동시 다종목 포트폴리오 시뮬레이션
- 일별 순서: **청산 처리 → 진입 처리 → 스크리닝(순위 갱신) → 잔고 평가**

### 7.2 일별 처리 순서 상세

**STEP 1: 청산 처리**

현재 보유 포지션 중 아래 조건 중 하나라도 해당 시 청산:

| 우선순위 | 청산 조건 | 체결가 | 사유 |
|----------|----------|--------|------|
| 1 | today_low ≤ hard_stop_price | hard_stop_price | Hard Stop (방어선 붕괴) |
| 2 | ticker NOT IN current_target_tickers | today_open | 주도주 순위 이탈 (Switching) |
| 3 | execute_exit_T_plus_1 == True | today_open | 추세 이탈 (SMA선) |

**STEP 2: 진입 처리 (Dynamic Cash Sweep)**

```python
# 예수금 거의 100% 투입 (0.2% 수수료 버퍼만 제외)
target_invest = capital × 0.998
qty = int(target_invest // today_open)  # 정수 주식수
cost = qty × today_open
capital -= cost
```

- `execute_buy_T_plus_1 == True` 이고 현재 미보유 종목만 진입
- 체결가: **당일 시가(open)**

**매수 사유 자동 분류:**
- `is_bull_market == True`: "Turbo-K 가속 진입 (유동성 확인)"
- 그 외: "기본 돌파 매수"

**STEP 3: 주도주 스크리닝 (매일 갱신)**

```python
# composite_rs 기준 내림차순 정렬
rs_scores = {ticker: composite_rs for each ticker in today_rows}
sorted_tickers = sorted(rs_scores, key=composite_rs, reverse=True)
current_target_tickers = sorted_tickers[:max_tickers]  # Top N
```

- 매일 갱신 (금요일 제한 없음 — V3.4.0에서 완전 매일 스위칭으로 변경)
- NaN, Inf 값은 스크리닝에서 제외

**STEP 4: 잔고 평가**

```python
daily_value = cash + Σ(qty × today_close)  for each position
portfolio_history.append({'date': current_date, 'total_value': daily_value})
```

### 7.3 성과 지표 계산

**누적 수익률:**
```
cumulative_return = (final_capital / initial_capital - 1) × 100
```

**CAGR (연평균 복리 수익률):**
```
years = (end_date - start_date).days / 365.25  (최소 0.5년)
CAGR = (final_capital / initial_capital)^(1/years) - 1) × 100
```

**MDD (최대 낙폭):**
```
peak      = total_value.cummax()
drawdown  = (total_value - peak) / peak
MDD       = drawdown.min() × 100
```

### 7.4 매매일지 (trade_logs)

각 청산 시 기록:

| 필드 | 내용 |
|------|------|
| 종목명 | ETF 이름 |
| 진입일자 | 매수 체결일 |
| 매입사유 | "기본 돌파 매수" / "Turbo-K 가속 진입" |
| 진입단가 | 매수 시가 |
| 매수수량 | 주식 수 |
| 청산일자 | 매도 체결일 |
| 매매사유 | Hard Stop / 순위 이탈 / 추세 이탈 |
| 청산단가 | 매도 체결가 |
| 수익률(%) | (청산단가/진입단가 - 1) × 100 |
| 수익금액 | qty × (청산단가 - 진입단가) |

---

## 8. 데이터베이스 스키마

### 8.1 market_data

```sql
CREATE TABLE market_data (
    date     DATE    NOT NULL,
    ticker   VARCHAR NOT NULL,
    open     DECIMAL,
    high     DECIMAL,
    low      DECIMAL,
    close    DECIMAL,
    volume   BIGINT,
    mfi      DECIMAL,              -- MFI 14일
    intraday_intensity DECIMAL,   -- Intraday Intensity
    PRIMARY KEY (date, ticker)
);
```

### 8.2 daily_signals

```sql
CREATE TABLE daily_signals (
    id                  SERIAL PRIMARY KEY,
    signal_date         DATE NOT NULL,
    ticker              VARCHAR(50) NOT NULL,
    close               NUMERIC,
    target_break_price  NUMERIC,
    composite_rs        NUMERIC,
    buy_signal          BOOLEAN,
    exit_signal         BOOLEAN,
    mfi                 NUMERIC,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(signal_date, ticker)
);
```

### 8.3 backtest_cache_meta

```sql
CREATE TABLE backtest_cache_meta (
    id                SERIAL PRIMARY KEY,
    app_version       VARCHAR NOT NULL,
    max_tickers       INT NOT NULL,
    end_date          DATE NOT NULL,
    cumulative_return DECIMAL,
    cagr              DECIMAL,
    mdd               DECIMAL,
    final_capital     DECIMAL,
    stored_at         TIMESTAMP DEFAULT NOW(),
    UNIQUE(app_version, max_tickers)
);
```

### 8.4 backtest_history_cache

```sql
CREATE TABLE backtest_history_cache (
    id           SERIAL PRIMARY KEY,
    app_version  VARCHAR NOT NULL,
    max_tickers  INT NOT NULL,
    date         DATE NOT NULL,
    total_value  DECIMAL,
    UNIQUE(app_version, max_tickers, date)
);
```

### 8.5 backtest_trades_cache

```sql
CREATE TABLE backtest_trades_cache (
    id           SERIAL PRIMARY KEY,
    app_version  VARCHAR NOT NULL,
    max_tickers  INT NOT NULL,
    ticker       VARCHAR,
    entry_date   DATE,
    buy_reason   VARCHAR,
    entry_price  DECIMAL,
    qty          INT,
    exit_date    DATE,
    exit_reason  VARCHAR,
    exit_price   DECIMAL,
    return_pct   DECIMAL,
    profit_amt   DECIMAL
);
```

### 8.6 backtest_history

```sql
-- 일별 포트폴리오 요약 (앱 실행 시 매일 upsert)
CREATE TABLE backtest_history (
    record_date        DATE UNIQUE NOT NULL,
    cumulative_return  NUMERIC,
    cagr               NUMERIC,
    mdd                NUMERIC,
    version            VARCHAR(20),
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 8.7 live_trades

```sql
-- 실전 체결가 vs 알고리즘 신호가 괴리 추적
CREATE TABLE live_trades (
    id            SERIAL PRIMARY KEY,
    signal_date   DATE NOT NULL,
    execute_date  DATE NOT NULL,
    ticker        VARCHAR(50) NOT NULL,
    action        VARCHAR(20) NOT NULL,  -- 'Buy', 'Sell', 'Reject_Buy', 'Reject_Sell'
    algo_price    NUMERIC NOT NULL,
    real_price    NUMERIC NOT NULL,
    quantity      INTEGER NOT NULL,
    status        VARCHAR(20) DEFAULT 'Completed',
    created_at    TIMESTAMP DEFAULT timezone('utc', now())
);
```

---

## 9. 프론트엔드 UI 구성

### 9.1 전역 레이아웃

```
st.set_page_config(layout="wide")
제목: "🔥 KODEX IRP 실전 매매 컨트롤 타워 (V3.5.x Stable)"

사이드바:
  - max_tickers 선택 (3 / 5 / 10)
  - 무결성 배지: ✅ 데이터 무결성 검증 완료
  - 실전 신호 새로고침 🔄 버튼
      → load_live_signals_only.clear() + load_k200_benchmark.clear() + st.rerun()

최신 타점 갱신일 표시
시스템 엔진 상태: 🚀 터보 가속 ON / 🛡️ 안정 모드
```

### 9.2 Tab 1: 🚀 AI 실전 시그널 보드

**구성:**
- 22개 종목을 composite_rs 순으로 정렬
- 상위 max_tickers 종목을 "매수 대상" 하이라이트
- 종목별 카드 (3열 배치):

| 표시 항목 | 내용 |
|-----------|------|
| 종목명 + 티커 | |
| Composite RS | 주도주 점수 |
| 현재가 | 전일 종가 |
| 목표 돌파가 | target_break_price |
| ① 가격 돌파 | close ≥ target_break_price |
| ② MFI | mfi ≥ 종목별 임계값 |
| ③ Intraday Intensity | > 0 여부 |
| ④ ADX 추세 강도 | adx_14 ≥ 종목별 임계값 |
| 신호 뱃지 | 🟢BUY / 🟡매수대기 / ⚪관망 |
| 결론 뱃지 | 🚀4/4 / ⏳3/4 / 💤0~2/4 |

**신호 판정 기준:**

| 뱃지 | 조건 |
|------|------|
| 🟢 BUY/HOLD | 4조건 모두 충족 |
| 🟡 매수대기 | 3조건 충족 |
| ⚪ 관망/준비 | 2조건 이하 |

### 9.3 Tab 2: 📊 성과 분석

**구성 요소:**

1. **포트폴리오 성과 메트릭 (st.metric)**
   - 초기자본 / 최종자본 / 누적수익률 / CAGR / MDD

2. **누적 수익률 차트 (Plotly Line)**
   - X축: 날짜, Y축: 포트폴리오 총액
   - DB 캐시 `backtest_history_cache`에서 로드

3. **연간 수익률 테이블**
   - 열: 연도 / IRP수익률(%) / KOSPI200(%) / Alpha(pp)
   - TOTAL 행 포함
   - KOSPI200: `load_k200_benchmark()` (TTL 86400s)
   - bm_df 실패 시 N/A 표시 (방어 로직)

4. **매매일지 다운로드**
   - `backtest_trades_cache`에서 로드
   - Excel 다운로드 버튼

### 9.4 Tab 3: 🩺 투명한 하이브리드 엔진 설계도

**구성 요소:**

1. **전일 시장 레짐 판독 엔진 정보판**
   - STEP 1: ADX 현재값 / μ / σ
   - STEP 2: Z-Score + 임계값 비교 (✅/❌)
   - STEP 3: MFI + 임계값 비교 (✅/❌)
   - STEP 4: 최종 판정 + 히스테리시스 설명
   - 현재 레짐의 K값 공식 + 청산선 표시

2. **TICKER_PARAMS 테이블**
   - 22종목 전체 K/MFI임계/ADX임계 공시

3. **Composite RS 무결성 테이블**
   - 종목별: 현재가 / RS_20 / 정배열 점수 / composite_rs / 진입조건 충족여부

### 9.5 캐시 전략

| 함수 | TTL | 용도 |
|------|-----|------|
| `load_live_signals_only()` | 3600s (1h) | 실전신호 |
| `load_k200_benchmark()` | 86400s (24h) | KOSPI200 벤치마크 |
| `get_single_ticker_data()` | 1800s (30min) | 개별종목 데이터 |
| `load_backtest_from_db_cache()` | 3600s (1h) | Supabase 백테스트 캐시 |

**실전 신호 새로고침 버튼:** `load_live_signals_only` + `load_k200_benchmark` 만 clear (백테스트 DB 캐시 보존)

---

## 10. 배포 환경

### 10.1 Streamlit Community Cloud

- GitHub 저장소 연동: `plnman/KODEXETF_SS`
- 브랜치: `main`
- 엔트리: `frontend/app.py`
- Python: 3.x (자동)
- 환경변수: Streamlit Secrets에 Supabase URL + KEY 등록

### 10.2 requirements.txt 필수 패키지

```
streamlit
pandas
numpy
plotly
FinanceDataReader
supabase
python-dotenv
requests
```

### 10.3 환경변수

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJhbGci...
```

---

## 11. 무결성 및 검증

### 11.1 데이터 무결성 검증 (KRX vs Naver 실측)

`compare_krx_vs_naver.py` 실행 결과 (2026-04-07 기준):

| 항목 | 결과 |
|------|------|
| 검증 종목 | 21개 |
| 전체 데이터포인트 | 31,790건 |
| 완전일치 | **31,790건 (100.00%)** |
| 불일치 | **0건** |

→ **FDR(KRX)과 Naver Finance는 동일 원천(KRX 공식 체결 데이터) 사용 확인**

### 11.2 백테스트 무결성 선언

1. **절대 수정 금지 함수:**
   - `run_portfolio_backtest()` — `portfolio_backtester.py`
   - `calculate_mfi()` — `daily_scraper.py`
   - `calculate_intraday_intensity()` — `daily_scraper.py`

2. **데이터 동기화 방식:**
   - 모든 개별종목은 KODEX200 날짜 축으로 reindex + ffill
   - 중복 날짜 제거: `drop_duplicates(subset=['date'])`

3. **무결성 감사 로그:** `analytics/backtest_audit_log.json` (최근 100건 유지)

### 11.3 백테스트 결과 캐싱 키

```
캐시 식별: app_version + max_tickers
예: V3.5.13 + 5 → 362.84%

버전 변경 시 → 새로운 캐시 키 → 자동 재계산 후 저장
```

---

## 12. 봉인된 확정값

아래 수치는 시스템의 기준값으로, 알고리즘 변경 없이 변동되어서는 안 됨:

| 항목 | 값 | 비고 |
|------|-----|------|
| 백테스트 기간 | 2019-01-02 ~ 2026-04-04 | |
| 정합 거래일수 | 1,781행 | KODEX200 기준 |
| 5종목 누적수익률 | 362.84% | STABLE_ROI |
| 3종목 누적수익률 | 43.91% | |
| 10종목 누적수익률 | 187.96% | |
| ATR_MULTIPLIER | 3.0 | 하드 스탑 배수 |
| TURBO_DISCOUNT (개별) | 0.4 | Bull 레짐 K 할인율 |
| TURBO_DISCOUNT (K200) | 0.5 | 레짐 판단용 |
| Bull 진입 Z 임계 | 2.0 | |
| Stable 복귀 Z 임계 | 1.0 | |
| Bull 진입 MFI 임계 | 40 | |
| 최소 투자 버퍼 | 0.2% | 수수료 공제 |
| 실전 룩백 기간 | 500일 | 280 거래일 워밍업 보장 |

---

*본 사양서는 V3.5.13 기준으로 작성됨. 알고리즘 변경 시 해당 섹션 업데이트 필요.*
