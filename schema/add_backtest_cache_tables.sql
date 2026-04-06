-- [V3.5.7] 백테스트 DB 캐시 테이블 (실전신호 + 백테스트 분리 아키텍처)
-- Supabase SQL Editor에서 실행

-- 1. 캐시 메타 (수익률 지표 + 유효성 키)
CREATE TABLE IF NOT EXISTS backtest_cache_meta (
    id SERIAL PRIMARY KEY,
    app_version VARCHAR NOT NULL,
    max_tickers INT NOT NULL,
    end_date DATE NOT NULL,
    cumulative_return DECIMAL,
    cagr DECIMAL,
    mdd DECIMAL,
    final_capital DECIMAL,
    stored_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(app_version, max_tickers)
);

-- 2. 일별 포트폴리오 히스토리 (Tab 2 차트용)
CREATE TABLE IF NOT EXISTS backtest_history_cache (
    id SERIAL PRIMARY KEY,
    app_version VARCHAR NOT NULL,
    max_tickers INT NOT NULL,
    date DATE NOT NULL,
    total_value DECIMAL,
    UNIQUE(app_version, max_tickers, date)
);

-- 3. 매매일지 (Tab 2 트레이드 로그용)
CREATE TABLE IF NOT EXISTS backtest_trades_cache (
    id SERIAL PRIMARY KEY,
    app_version VARCHAR NOT NULL,
    max_tickers INT NOT NULL,
    ticker VARCHAR,
    entry_date DATE,
    buy_reason VARCHAR,
    entry_price DECIMAL,
    qty INT,
    exit_date DATE,
    exit_reason VARCHAR,
    exit_price DECIMAL,
    return_pct DECIMAL,
    profit_amt DECIMAL
);

CREATE INDEX IF NOT EXISTS idx_bt_cache_meta   ON backtest_cache_meta(app_version, max_tickers);
CREATE INDEX IF NOT EXISTS idx_bt_cache_hist   ON backtest_history_cache(app_version, max_tickers, date);
CREATE INDEX IF NOT EXISTS idx_bt_cache_trades ON backtest_trades_cache(app_version, max_tickers, entry_date);
