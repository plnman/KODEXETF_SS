-- KODEX 안티그래비티 초기 데이터베이스 스키마
-- Supabase SQL Editor에서 실행하거나 마이그레이션 스크립트를 통해 자동 실행됩니다.

-- 1. 종목 마스터 테이블 (테스트/상폐 종목 추적 포함)
CREATE TABLE IF NOT EXISTS tickers (
    symbol VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_inverse BOOLEAN DEFAULT FALSE,
    is_leverage BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 2. 일봉 OHLCV 테이블 (성능을 위해 symbol과 date에 타임스케일/인덱스 활용)
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) REFERENCES tickers(symbol) ON DELETE CASCADE,
    date DATE NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT,
    UNIQUE(symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_symbol_date ON daily_ohlcv(symbol, date);

-- 3. CVD (체결강도) 요약 테이블 (1분봉 데이터 용량 한계를 극복하기 위한 일별 CVD 적재 테이블)
CREATE TABLE IF NOT EXISTS cvd_summary (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) REFERENCES tickers(symbol) ON DELETE CASCADE,
    date DATE NOT NULL,
    cvd_score NUMERIC DEFAULT 0,  -- 최종 일일 누적 CVD 스코어
    cumulative_buy_volume BIGINT DEFAULT 0, -- 체결 매수 총합
    cumulative_sell_volume BIGINT DEFAULT 0, -- 체결 매도 총합
    UNIQUE(symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_cvd_summary_symbol_date ON cvd_summary(symbol, date);
