-- 기존 잔재물인 1분봉/일봉 혼합 테이블 깔끔하게 제거
DROP TABLE IF EXISTS daily_ohlcv;
DROP TABLE IF EXISTS cvd_summary;

-- IRP 전용 통합 일봉(Daily-Only) 테이블 생성 (추가 파생지표 내장)
CREATE TABLE market_data (
    date DATE NOT NULL,
    ticker VARCHAR NOT NULL,
    open DECIMAL,
    high DECIMAL,
    low DECIMAL,
    close DECIMAL,
    volume BIGINT,
    mfi DECIMAL,
    intraday_intensity DECIMAL,
    PRIMARY KEY (date, ticker)
);

-- 백테스트 및 스크리닝 쿼리 속도 극대화를 위한 인덱싱
CREATE INDEX idx_market_data_ticker ON market_data(ticker);
CREATE INDEX idx_market_data_date ON market_data(date);
