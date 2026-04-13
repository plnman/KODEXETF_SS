# KODEX IRP 매매 컨트롤 타워 — Claude 작업 가이드

## 프로젝트 개요
- KODEX ETF 기반 IRP 계좌 실전 매매 신호 시스템
- Streamlit 단일 페이지 앱 (V3.8.0)
- 데이터: FinanceDataReader (FDR) — Yahoo Finance 영구 퇴출
- DB: Supabase (PostgreSQL)
- 배포: Streamlit Community Cloud

## 배포 URL
https://kodexetfss-9civ4tvzx4qymaewzpxjyu.streamlit.app/

## Git 저장소
- 로컬 경로: `C:\Users\kim.ss\Projects\Claude_KODEX_SS\app`
- 원격: https://github.com/plnman/KODEXETF_SS

---

## ⚠️ 필수 작업 프로세스 (반드시 준수)

### 코드 수정 후 배포 순서

```
1. 코드 수정
2. 로컬 서버 실행: bash run_local.sh
3. 브라우저에서 http://localhost:8501 확인
4. 체크리스트 통과 후에만 push
5. git push
6. 웹 배포 확인 (2~3분 후)
```

### 로컬 확인 체크리스트
- [ ] Tab 1: AI 실전 시그널 보드 — 5개 카드 정상 표시
- [ ] Tab 2: 백테스팅 결과 — 누적수익률 200.82% (5종목 기준, V3.8.0 확정)
- [ ] Tab 3: 알고리즘 무결성 진단 — TICKER_PARAMS 15종목 전부 표시
- [ ] Tab 4: 실전 성과 궤적 — DB 연결 오류 없음
- [ ] 무결성 점수 100%, 데이터 1781 rows, 수익률 정밀 오차 ±0.00%

---

## 절대 수정 금지 구역

| 파일 | 금지 내용 |
|---|---|
| `analytics/portfolio_backtester.py` | 수익률 연산 산식 전체 |
| `analytics/backtester.py` | 벡터라이징 백테스트 로직 |
| `data_collector/daily_scraper.py` | MFI, Intraday Intensity 계산 |
| `engine/strategy.py` | 신호 생성 로직 전체 |

디버깅 및 버그 수정은 허용. 설계/파라미터 변경은 사용자 명시적 요청 시에만.

---

## 핵심 파라미터 (현재 설정)

| 항목 | 값 |
|---|---|
| 기본 운용 모드 | 5종목 균형 투자 (index=1) |
| 유니버스 | 15종목 (국내 4 + 글로벌 3 + AI/테크 5 + 방산/우주/로봇 3) [V3.8.0] |
| 백테스트 기간 | 2019-01-02 ~ 2026-04-04 (1781 rows) |
| 초기 자본 | 5,000만원 |
| turbo_discount (K200) | 0.5 |
| turbo_discount (개별 종목) | 0.4 |
| ATR_MULTIPLIER | 2.5 |

### BASELINE_RET_MAP (무결성 검증 기준값)
```python
# [V3.8.0 확정] 15종목 신규 유니버스 (2019-01-02 ~ 2026-04-03)
{3: 181.51, 5: 200.82, 10: 399.13}
```

---

## 알려진 설계 이슈 (미해결)

### 3-ticker < 5-ticker 역전 현상
- 원인: V3.5.0 글로벌 ETF 추가로 인해 나스닥100/FANG+ 등이 불장에서 RS 상위 독점
- 3-ticker 모드에서 전량 스위칭 반복 → 수익률 파괴
- 국내 10종목만 사용 시: 3(505%) > 5(446%) > 10(397%) 정상 순서 확인
- 현재 대응: 5종목을 기본값으로 운용

### 향후 개선 검토 항목
1. RS 지속성 필터 — N일 연속 상위권 유지 시에만 스위칭 발동
2. 국내/해외 쿼터제 — 슬롯 분리 (예: 국내 3 + 글로벌 2)
3. 스위칭 쿨다운 — 진입 후 최소 N거래일 스위칭 청산 면제

---

## 주요 파일 구조

```
app/
├── config/
│   └── etf_universe.py      # [V3.8.0] Single Source of Truth — 종목 추가/변경은 이 파일만!
├── frontend/app.py          # Streamlit 메인 앱
├── engine/strategy.py       # 신호 생성 엔진 (NEVER TOUCH)
├── analytics/
│   ├── portfolio_backtester.py  # 멀티티커 백테스터 (NEVER TOUCH)
│   ├── backtester.py            # 단일 티커 벡터 백테스터
│   └── integrity_monitor.py     # 무결성 모니터
├── data_collector/
│   ├── daily_scraper.py     # FDR 데이터 수집 + MFI/II 계산
│   └── supabase_client.py   # DB 연결
├── run_local.sh             # 로컬 서버 실행 스크립트
└── deploy.sh                # Git 배포 스크립트
```

## [V3.8.0] Single Source of Truth 설계

종목 추가/제거 방법:
1. `config/etf_universe.py`의 `ETF_UNIVERSE` 딕셔너리에 항목 추가/삭제
2. 저장 후 끝 — daily_scraper.py, strategy.py, app.py 수정 불필요

특수 코드 (SKIP_LISTING_CHECK 자동 포함):
- 영숫자 혼합 코드 (예: 0080G0, 0167Z0, 0151S0, 0173Y0, 0038A0)는 `.KS` 없이 입력
- isdigit() 로직으로 자동 감지하여 FDR 리스팅 대조 제외

---

## Supabase 테이블 구조
- `market_data` — OHLCV + MFI + II (일별)
- `daily_signals` — 22종목 신호 (buy_signal, exit_signal, composite_rs 등)
- `backtest_history` — 일별 누적수익률 기록
- `backtest_history_naver` — 네이버 이중화 수익률 기록
