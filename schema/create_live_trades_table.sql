-- 실전 체결 내역과 괴리율을 추적하기 위한 Supabase DB 테이블 신설 스크립트
CREATE TABLE IF NOT EXISTS live_trades (
    id SERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    execute_date DATE NOT NULL,
    ticker VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL, -- 'Buy', 'Sell', 'Reject_Buy', 'Reject_Sell'
    algo_price NUMERIC NOT NULL,
    real_price NUMERIC NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'Completed',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);
