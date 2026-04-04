-- 🚦 V3.5.0 이중 데이터 검증 (Dual-Source Integrity) 전용 테이블

-- 1. 네이버(FDR) 기반 일별 종목별 시그널 데이터 적재 테이블
CREATE TABLE IF NOT EXISTS daily_signals_naver (
    id SERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    ticker VARCHAR(50) NOT NULL,
    close NUMERIC,
    target_break_price NUMERIC,
    composite_rs NUMERIC,
    buy_signal BOOLEAN,
    exit_signal BOOLEAN,
    mfi NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(signal_date, ticker)
);

-- 2. 네이버(FDR) 기반 포트폴리오 백테스팅 요약 테이블
CREATE TABLE IF NOT EXISTS backtest_history_naver (
    id SERIAL PRIMARY KEY,
    record_date DATE UNIQUE NOT NULL,
    cumulative_return NUMERIC,
    cagr NUMERIC,
    mdd NUMERIC,
    version VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- RLS 활성화 및 권한 설정 (개발/테스트 용도)
ALTER TABLE daily_signals_naver ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Enable all ops on daily_signals_naver" ON daily_signals_naver FOR ALL USING (true);

ALTER TABLE backtest_history_naver ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Enable all ops on backtest_history_naver" ON backtest_history_naver FOR ALL USING (true);
