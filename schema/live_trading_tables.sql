-- ============================================================
-- KODEX IRP 실전 매매 추적 테이블 (V3.6.1, 2026-04-08 시작)
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1. 실전 매매 체결 기록
CREATE TABLE IF NOT EXISTS live_trades (
    id              BIGSERIAL PRIMARY KEY,
    signal_date     DATE        NOT NULL,   -- 신호 발생일
    execute_date    DATE        NOT NULL,   -- 실제 매매일 (시가 기준)
    ticker          VARCHAR(100) NOT NULL,
    action          VARCHAR(10)  NOT NULL,  -- 'BUY' or 'EXIT'
    execute_price   DECIMAL(12,2),          -- 시가 (진입/청산가)
    signal_close    DECIMAL(12,2),          -- 신호일 종가
    units           DECIMAL(14,6) DEFAULT 0, -- 매수/매도 수량
    amount          DECIMAL(15,2) DEFAULT 0, -- 거래 금액
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(signal_date, ticker, action)
);

-- 2. 일별 포트폴리오 가치 이력
CREATE TABLE IF NOT EXISTS live_portfolio_history (
    id               BIGSERIAL PRIMARY KEY,
    date             DATE        NOT NULL UNIQUE,
    total_value      DECIMAL(15,2) NOT NULL, -- 총 포트폴리오 가치
    cash             DECIMAL(15,2) NOT NULL, -- 현금 잔액
    positions_value  DECIMAL(15,2) NOT NULL, -- 보유 종목 평가액
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- 초기값: 오늘(시작일) 포트폴리오 = 현금 5,000만원
INSERT INTO live_portfolio_history (date, total_value, cash, positions_value)
VALUES ('2026-04-08', 50000000, 50000000, 0)
ON CONFLICT (date) DO NOTHING;
