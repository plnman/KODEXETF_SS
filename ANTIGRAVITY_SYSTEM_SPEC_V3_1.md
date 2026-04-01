# 💎 [SYSTEM SPEC] V3.1 지능형 하이브리드 매매 엔진 초정밀 설계 명세서

본 문서는 KODEX IRP 무결성 매매 시스템(V3.1)의 모든 기술적 세부사항을 담은 **'최종 설계 도면(Full Blueprint)'**입니다. 본 명세서는 코드를 보지 않고도 동일한 엔진을 100% 재현할 수 있도록 수학적 수식과 논리 흐름을 극한으로 상세화했습니다.

---

## 1. 🛡️ 시스템 아키텍처 및 운용 철학

### 1.1 무결성 원칙 (Integrity Protocol)
- **Single Source of Truth (SSoT):** 백테스팅 엔진과 실전 매매 UI는 동일한 `engine/strategy.py` 모듈을 공유함.
- **T+1 Execution:** 모든 지표는 $T$일 종가(15:40) 기준으로 확정하며, 실제 주문은 $T+1$일 09:00 시가(Open)에 집도함. (Look-ahead Bias 0%)
- **Hybrid Regime Control:** 시장의 에너지 강도(Volatility Intensity)에 따라 진입/청산 로직을 동적으로 스위칭하는 하이브리드 구조.

### 1.2 데이터 타임라인 (Decision Sequence)
1.  **15:40 (T일):** 당일 종가 데이터 수집 및 MFI, II, ADX 등 보조지표 확정 연산.
2.  **15:41 (T일):** 레짐(Bull/Stable) 판독 및 종목별 매수/매도 시그널 생성.
3.  **익일 09:00 (T+1일):** 전일 생성된 시그널에 따라 시장가(Market Order) 진입 또는 청산.

---

## 2. 🔬 데이터 엔지니어링: 보조지표 수학 공식

엔진이 사용하는 모든 지표는 다음의 엄격한 수학적 규격을 따릅니다.

### 2.1 수급 지표 (Volume-Price Logic)
- **MFI (Money Flow Index):**
    - $Typical Price (TP) = \frac{High + Low + Close}{3}$
    - $Raw Money Flow (RMF) = TP \times Volume$
    - $Positive Flow (14d) = \sum_{i=1}^{14} RMF_i \text{ if } TP_i > TP_{i-1}$
    - $Negative Flow (14d) = \sum_{i=1}^{14} RMF_i \text{ if } TP_i < TP_{i-1}$
    - $MFI = 100 - (\frac{100}{1 + \frac{PositiveFlow}{NegativeFlow}})$
- **Intraday Intensity (II):** 장중 세력의 가격 지배력을 측정함.
    - $II = \frac{2 \times Close - High - Low}{High - Low} \times Volume$
    - (분모가 0일 경우 $0.001$로 보정하여 연산 오류 방지)

### 2.2 변동성 및 추세 지표 (Volatility Logic)
- **ATR (Average True Range):** 14일 Wilder's Smoothing 적용.
    - $TR = \max(High - Low, |High - Close_{prev}|, |Low - Close_{prev}|)$
    - $ATR_{14} = EWM(TR, \alpha=\frac{1}{14}, \text{min\_periods}=14)$
- **ADX (Average Directional Index):** 횡보장 필터링 핵심 지표.
    - $+DM, -DM$ 산출 후 Wilder's Smoothing ($\alpha=\frac{1}{14}$) 적용.
    - $DX = 100 \times \frac{|+DI - -DI|}{+DI + -DI}$
    - $ADX_{14} = EWM(DX, \alpha=\frac{1}{14})$

---

## 3. 🧠 지형 판독 레이어: ADX Z-Score 레짐 스위칭

시장이 '불장(Bull)'인지 '안정장(Stable)'인지 판독하는 핵심 로직입니다.

### 3.1 Z-Score 연산 (Regime Calculation)
- **관측 윈도우(Lookback):** 최근 252일 (약 1년 거래일)
- **공식:** $Z = \frac{ADX_{14} - \mu_{252}}{\sigma_{252}}$
- $\mu_{252}$: 252일 ADX 이동평균 / $\sigma_{252}$: 252일 ADX 표준편차.

### 3.2 히스테리시스 스위칭 (Hysteresis Buffer)
빈번한 레짐 변경(Whipsaw)을 막기 위해 상하단 임계치를 다르게 설정합니다.
- **Bull 진입:** $Z > 2.0$ (강력한 추세 폭발 시점)
- **Stable 복귀:** $Z < 1.0$ (에너지가 평균 수준으로 수렴 시)

---

## 4. 🎯 매매 프로세스: 진입 및 청산 알고리즘

### 4.1 지능형 가변 돌파 (Dynamic Entry K)
진동의 크기에 따라 진입 장벽을 스스로 높이거나 낮춥니다.
- **기본 가중치:** $K_{adj} = K_{base} \times \frac{\sigma_{20}}{\sigma_{252}}$
- **범위 제한:** $0.2 \le K_{adj} \le 0.8$
- **V3.1 불장 가속기:** 레짐이 `Bull`일 경우 $K_{adj}$를 **20% 할인(0.8배)**하여 선제적 추격 매수.
- **진입 조건 ($T$일 종가 기준):**
    - `Close > Open + (PrevRange * K_adj)` **AND**
    - `MFI > Threshold` **AND**
    - `II > 0` **AND**
    - `ADX_14 > Threshold`

### 4.2 종목별 다이내믹 청산 (Adaptive Exit)
종목의 변동성 순위(`vol_rank`)에 따라 청산 방어선을 유연하게 변경합니다.
- **Relative Volatility:** $RelVol = \frac{ATR_{14}}{Close}$
- **Volatility Rank (252d):** 최근 1년 중 현재 종목의 상대적 변동성 백분위(0.0~1.0).
- **청산 로직:**
    1.  **Case Market Bull:** **SMA 10(10일 이동평균선)** 깨지면 즉시 익절.
    2.  **Case Stable + Low Vol (vol_rank < 30%):** **SMA 10** 기준 (무거운 종목은 빠른 대응).
    3.  **Case Stable + High Vol (vol_rank >= 30%):** **SMA 20** 기준 (가벼운 종목은 휩쏘 방지).

---

## 5. 📒 전 종목 최적화 파라미터 매트릭스 (Registry)

Grid Search(720회 시뮬레이션)를 통해 도출된 V3.1 지능형 엔진 전용 황금 수치입니다.

| 종목명 (Ticker) | Base K | MFI Thr | ADX Thr | 엑시트 성향 |
| :--- | :---: | :---: | :---: | :--- |
| **KODEX 2차전지산업** | **0.3** | 60 | 20 | 공격적 추세 추종 |
| **KODEX 코스닥150** | **0.2** | 50 | 15 | 고변동 가속 진입 |
| **KODEX 반도체** | **0.2** | 50 | 15 | 고변동 가속 진입 |
| **KODEX 200** | **0.7** | 40 | 15 | 저변동 안정 수성 |
| **KODEX 은행** | **0.7** | 65 | 20 | 보수적 진입 필터 |
| **KODEX 자동차** | **0.2** | 50 | 15 | 고변동 가속 진입 |
| **KODEX 건설** | **0.4** | 60 | 15 | 낙폭과대 반등 추적 |
| **KODEX 금융** | **0.5** | 60 | 20 | 중립적 추세 필터 |
| **KODEX 기계장비** | **0.7** | 65 | 15 | 보수적 진입 필터 |
| **KODEX 철강** | **0.3** | 40 | 15 | 중기 추세 추종 |

---

## 6. 🚀 신규 시장(미장 등) 이식 시 체크리스트

1.  **데이터 무결성:** 일봉 O,H,L,C,V 데이터가 빈틈없이 로드되는지 확인 (yfinance 또는 로컬 DB).
2.  **레짐 지수 설정:** 해당 시장의 지수(예: QQQ, SPY) ADX Z-Score를 전체 엔진의 `is_bull` 인자로 주입.
3.  **그리드 최적화 실행:** `analytics/grid_optimizer.py`를 통해 해당 시장 종목에 맞는 `K`, `MFI`, `ADX` 파라미터를 최소 500회 이상 시뮬레이션하여 재산출.
4.  **T+1 체결 검증:** 해외 주식의 경우 시차로 인한 $T+1$일 아침 시가 주문이 정상적으로 대기열에 들어가는지 통제.

---
> **"본 10배 상세 명세서는 V3.1 하이브리드 엔진의 영혼을 담고 있습니다. 숫자로 정의된 로직은 주관을 배제하며, 오직 데이터에 기반한 무결성 수익의 궤적만을 추구합니다."**
