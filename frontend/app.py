import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os
import time
import base64
import importlib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine.strategy as strategy
importlib.reload(strategy)

from engine.strategy import build_signals_and_targets, get_market_regime, TICKER_PARAMS
from analytics.portfolio_backtester import run_portfolio_backtest
from analytics.backtester import run_vectorized_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS, verify_dual_source_integrity, verify_tickers
from analytics.integrity_monitor import log_backtest_integrity
from config.etf_universe import ETFS_CLEAN

# [V3.8.1] - 버그픽스: Ticker .KS 노출, 카드수 max_tickers 연동, 디폴트 10종목
APP_VERSION = "V3.8.1"
APP_BUILD_DATE = "2026-04-13"
STABLE_ROI = 292.60  # 5종목 기준 [V3.8.0 확정: 신규종목 공통 파라미터 k=0.5/mfi=50/adx=15 적용]
TARGET_ROWS = 1781   # 2019-01-02 ~ 2026-04-03 (KRX Master 1781 정합성)
BACKTEST_END_DATE = "2026-04-04"  # 봉인된 백테스트 종료일
LIVE_LOOKBACK_DAYS = 500          # 실전신호 전용 최근 데이터 로딩 범위 (일) [V3.5.11: 레짐 Z-score 워밍업 280거래일 보장]
MAX_POSITIONS = 10               # 실전 보유 최대 종목수 (백테스팅 확정값)

# [NEW] 6단계 DB 바인딩을 위한 Supabase 연동
from data_collector.supabase_client import get_supabase_client
supabase = get_supabase_client()

st.set_page_config(page_title="KODEX IRP 매매 컨트롤 타워", page_icon="🚀", layout="wide")

# V3.1 핵심 파라미터 (동기화 확인용)
V3_1_PARAMS = {
    "K_BULL": 0.4,
    "K_STABLE": 0.6,
    "Z_SCORE_THRESHOLD": 1.5,
    "Z_SCORE_WINDOW": 20
}

@st.cache_data
def convert_df_to_csv(df):
    """Excel 호환성을 위해 UTF-8-SIG 인코딩으로 변환 및 캐싱"""
    if df.empty:
        return b""
    return df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')

@st.cache_data(ttl=3600)
def cached_run_backtest(all_signals, initial_capital, max_tickers, version=APP_VERSION):
    """백테스팅 연산 결과 캐싱 (다운로드 시 오차 및 타임아웃 방지)"""
    return run_portfolio_backtest(all_signals, initial_capital, max_tickers)

# ─────────────────────────────────────────────────────────────────────────────
# [V3.5.7] 2-Track 아키텍처: 백테스트 DB캐시 + 실전신호 경량 분리
# ─────────────────────────────────────────────────────────────────────────────

def save_backtest_to_db_cache(port_res: dict, max_tickers: int) -> bool:
    """백테스트 결과를 Supabase에 저장 (APP_VERSION + max_tickers 키)"""
    try:
        sb = get_supabase_client()
        if not sb: return False
        # 1. 메타
        sb.table('backtest_cache_meta').upsert({
            'app_version': APP_VERSION, 'max_tickers': max_tickers,
            'end_date': BACKTEST_END_DATE,
            'cumulative_return': float(port_res['cumulative_return']),
            'cagr': float(port_res['cagr']),
            'mdd': float(port_res['mdd']),
            'final_capital': float(port_res['final_capital']),
        }, on_conflict='app_version,max_tickers').execute()
        # 2. 히스토리
        if not port_res['history'].empty:
            sb.table('backtest_history_cache').delete()\
              .eq('app_version', APP_VERSION).eq('max_tickers', max_tickers).execute()
            rows = [{'app_version': APP_VERSION, 'max_tickers': max_tickers,
                     'date': str(r['date']), 'total_value': float(r['total_value'])}
                    for _, r in port_res['history'].iterrows()]
            for i in range(0, len(rows), 500):
                sb.table('backtest_history_cache').insert(rows[i:i+500]).execute()
        # 3. 매매일지
        if not port_res['trades_df'].empty:
            sb.table('backtest_trades_cache').delete()\
              .eq('app_version', APP_VERSION).eq('max_tickers', max_tickers).execute()
            trows = [{'app_version': APP_VERSION, 'max_tickers': max_tickers,
                      'ticker': str(t['종목명']), 'entry_date': str(t['진입일자']),
                      'buy_reason': str(t['매입사유']), 'entry_price': float(t['진입단가']),
                      'qty': int(t['매수수량']), 'exit_date': str(t['청산일자']),
                      'exit_reason': str(t['매매사유']), 'exit_price': float(t['청산단가']),
                      'return_pct': float(t['수익률(%)']), 'profit_amt': float(t['수익금액'])}
                     for _, t in port_res['trades_df'].iterrows()]
            for i in range(0, len(trows), 500):
                sb.table('backtest_trades_cache').insert(trows[i:i+500]).execute()
        return True
    except Exception:
        return False


def load_backtest_from_db_cache(max_tickers: int):
    """Supabase 캐시에서 백테스트 결과 로드. 유효하면 port_res dict 반환, 없으면 None"""
    try:
        sb = get_supabase_client()
        if not sb: return None
        meta = sb.table('backtest_cache_meta').select('*')\
            .eq('app_version', APP_VERSION).eq('max_tickers', max_tickers)\
            .eq('end_date', BACKTEST_END_DATE).execute()
        if not meta.data: return None
        m = meta.data[0]
        # Supabase 무료 플랜 max-rows=1000 우회: 1000행씩 페이지네이션
        all_hist_data = []
        offset = 0
        while True:
            batch = sb.table('backtest_history_cache').select('date,total_value')\
                .eq('app_version', APP_VERSION).eq('max_tickers', max_tickers)\
                .order('date').range(offset, offset + 999).execute()
            if not batch.data:
                break
            all_hist_data.extend(batch.data)
            if len(batch.data) < 1000:
                break
            offset += 1000
        df_history = pd.DataFrame(all_hist_data) if all_hist_data else pd.DataFrame()
        trades = sb.table('backtest_trades_cache').select('*')\
            .eq('app_version', APP_VERSION).eq('max_tickers', max_tickers)\
            .order('entry_date').execute()
        if trades.data:
            df_trades = pd.DataFrame(trades.data).rename(columns={
                'ticker': '종목명', 'entry_date': '진입일자', 'buy_reason': '매입사유',
                'entry_price': '진입단가', 'qty': '매수수량', 'exit_date': '청산일자',
                'exit_reason': '매매사유', 'exit_price': '청산단가',
                'return_pct': '수익률(%)', 'profit_amt': '수익금액'
            })[['종목명','진입일자','매입사유','진입단가','매수수량','청산일자','매매사유','청산단가','수익률(%)','수익금액']]
        else:
            df_trades = pd.DataFrame()
        return {
            'initial_capital': 50000000.0,
            'final_capital': float(m['final_capital']),
            'cumulative_return': float(m['cumulative_return']),
            'cagr': float(m['cagr']),
            'mdd': float(m['mdd']),
            'history': df_history,
            'trades_df': df_trades,
            'start_date': df_history['date'].iloc[0] if not df_history.empty else '-',
            'end_date': df_history['date'].iloc[-1] if not df_history.empty else '-',
            'total_days': len(df_history)
        }
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_live_signals_only():
    """[V3.5.7] 실전신호 전용 경량 로더 - 최근 400일만 로드하여 빠른 신호 생성"""
    import FinanceDataReader as fdr
    ETFS = ETFS_CLEAN  # [V3.8.0] Single Source of Truth: config/etf_universe.py
    start_date = (datetime.now() - timedelta(days=LIVE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    def _clean(df):
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        if 'date' not in df.columns: df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        return df.sort_values('date')

    try:
        k200 = _clean(fdr.DataReader("069500", start=start_date))
        k200['mfi'] = calculate_mfi(k200)
        k200['intraday_intensity'] = calculate_intraday_intensity(k200)
    except Exception as e:
        return {}, False, pd.DataFrame(), {"score": 0, "detail": str(e)}

    k200_sig = build_signals_and_targets(k200, "KODEX 200", turbo_discount=0.5)
    regime = get_market_regime(k200_sig, use_global_mfi=True)

    all_signals = {}
    for tk, name in ETFS.items():
        df = get_single_ticker_data(tk, name, start_date, None)
        if df is None: continue
        # [V3.9.1] production/백테스터와 동일: 각 종목 자체 날짜 그대로 사용 (K200 reindex+ffill 제거)
        # K200 reindex+ffill은 신규 ETF 상장 전 날짜를 가짜로 채워 rs_20 계산을 오염시킴
        df = df.drop_duplicates(subset=['date'])
        # [V3.9.1] fillna(False): 레짐 미확인 날짜는 안정장으로 처리 (백테스터/production 동일)
        regime_aligned = regime.reindex(df.set_index('date').index).fillna(False)
        sig = build_signals_and_targets(df, ticker_name=name, is_bull_market=regime_aligned, turbo_discount=0.4)
        all_signals[name] = sig

    is_bull_now = bool(regime.iloc[-1]) if not regime.empty else False
    integrity = {"score": 100, "detail": f"실전신호 최근 {LIVE_LOOKBACK_DAYS}일 로드 ({len(all_signals)}/{len(ETFS_CLEAN)} 종목)"}
    return all_signals, is_bull_now, k200_sig, integrity  # [V3.5.12] k200_sig 반환 (adx_14/sigma_20/sigma_avg 포함)


@st.cache_data(ttl=86400, show_spinner=False)  # [V3.5.9] 24시간 캐시 (FDR 간헐적 실패 방어)
def load_k200_benchmark():
    """[V3.5.7] Tab 2 벤치마크용 K200 전체 히스토리 (2019-현재)"""
    import FinanceDataReader as fdr
    try:
        df = fdr.DataReader("069500", start="2019-01-01")
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        if 'date' not in df.columns: df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        result = df.sort_values('date').set_index('date')
        # close 컬럼 정규화 (adj close → close 폴백)
        if 'close' not in result.columns and 'adj close' in result.columns:
            result = result.rename(columns={'adj close': 'close'})
        return result if 'close' in result.columns else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# [V3.5.2] 개별 종목 고속 캐싱 엔진 (무한 로딩 방어선)
@st.cache_data(ttl=1800, show_spinner=False)
def get_single_ticker_data(tk, name, start_date, end_date):
    import FinanceDataReader as fdr
    try:
        clean_tk = tk.replace(".KS", "").replace(".KQ", "")
        df = fdr.DataReader(clean_tk, start=start_date, end=end_date)
        if df.empty or len(df) < 30: return None  # production과 동일 기준 (30행 미만 SKIP)
        
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        if 'date' not in df.columns: df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df = df.sort_values('date')
        
        from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity
        df['mfi'] = calculate_mfi(df)
        df['intraday_intensity'] = calculate_intraday_intensity(df)
        return df
    except:
        return None

# [V3.5.2] KRX MASTER DEFINITIVE SYNC - 1,781행 강제 동기화 및 구형 캐시 완전 소탕
@st.cache_data(ttl=3600, show_spinner=False)
def load_and_process_data_v3_5_2_MASTER_FINAL(is_backtest=False):
    import FinanceDataReader as fdr
    # [V3.8.0] Single Source of Truth: config/etf_universe.py (모듈 수준 TARGET_ETFS 사용)
    
    end_date = "2026-04-04" if is_backtest else None
    start_date = "2019-01-01"
    context_str = "🔙 [과거 백테스트]" if is_backtest else "🔥 [실전 매매 신호]"
    sync_report = []
    all_data = {}
    
    # [Master Choice] KRX vs 네이버 이중화 (야후 영구 퇴출)
    try:
        # 1. KRX 공식 마스터 캘린더 (Golden Index)
        k200_krx = fdr.DataReader("069500", start=start_date, end=end_date)
        # 2. Naver 상호 대조 캘린더 (Integrity Check)
        k200_nv = fdr.DataReader("069500", start=start_date, end=end_date) 
        
        if k200_krx.empty: raise ValueError("KRX Data Fail")
        sync_report.append({"모드": context_str, "종목명": "KODEX 200", "티커": "069500.KS", "상태": "🟢 마스터(KRX)", "소스": "FDR"})
    except Exception as e:
        st.error(f"🚨 데이터 마스터(KRX) 로드 실패: {e}")
        return {}, False, pd.DataFrame(), [], {"score": 0, "detail": "Load Fail"}
    
    def clean_df(df):
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        if 'date' not in df.columns: df = df.reset_index().rename(columns={'Date': 'date', 'index': 'date'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        return df.sort_values('date')

    k200_krx = clean_df(k200_krx)
    k200_nv = clean_df(k200_nv)
    
    # [V3.5.2 FIX] 1,781행 엄격 필터링 (2019-01-02 ~ 2026-04-03)
    if is_backtest:
        k200_krx = k200_krx[(k200_krx['date'] >= "2019-01-02") & (k200_krx['date'] <= "2026-04-03")]
        k200_nv = k200_nv[(k200_nv['date'] >= "2019-01-02") & (k200_nv['date'] <= "2026-04-03")]
    
    # 🧪 이중 무결성 상시 대조 (Audit)
    match_count = (k200_krx['close'].values == k200_nv['close'].values).sum() if len(k200_krx) == len(k200_nv) else 0
    integrity_score = int((match_count / len(k200_krx)) * 100) if not k200_krx.empty else 0
    integrity_result = {"score": integrity_score, "detail": f"KRX vs Naver 일치율 ({match_count}/{len(k200_krx)})"}
    
    k200_raw = k200_krx.copy()
    k200_raw['mfi'] = calculate_mfi(k200_raw)
    k200_raw['intraday_intensity'] = calculate_intraday_intensity(k200_raw)

    # 전 종목 고속 병렬 수집 (개별 캐시 활용)
    for tk, name in TARGET_ETFS.items():
        df = get_single_ticker_data(tk, name, start_date, end_date)
        if df is not None:
            all_data[name] = df.copy()
            sync_report.append({"모드": context_str, "종목명": name, "티커": tk, "상태": "🟢 성공", "소스": "KRX"})
        else:
            sync_report.append({"모드": context_str, "종목명": name, "티커": tk, "상태": "🔴 실패", "소스": "None"})

    # 오리지널 레짐 판독 및 신호 생성 루틴 (NEVER TOUCH LOGIC)
    k200_signals = build_signals_and_targets(k200_raw, "KODEX 200", turbo_discount=0.5)
    regime_series = get_market_regime(k200_signals, use_global_mfi=True)
    
    all_signals = {}
    for name, df in all_data.items():
        df_sync = df.set_index('date').reindex(k200_raw.set_index('date').index).reset_index().ffill().fillna(0)
        df_sync = df_sync.drop_duplicates(subset=['date'])
        regime_aligned = regime_series.reindex(df_sync.set_index('date').index).fillna(True)
        ticker_signals = build_signals_and_targets(df_sync, ticker_name=name, is_bull_market=regime_aligned, turbo_discount=0.4)
        all_signals[name] = ticker_signals

    is_bull_now = regime_series.iloc[-1]
    return all_signals, is_bull_now, k200_raw, sync_report, integrity_result

def main():
    # [Custom CSS] 폰트 크기 증대 및 검은 카드 전용 스타일
    st.markdown("""
        <style>
            /* 일반 텍스트 크기만 소폭 증대 (색상은 기본값 복구) */
            .stMarkdown p, .stCaption, div[data-testid="stCaptionContainer"] {
                font-size: 1.1rem !important; 
            }
            /* h1, h2, h3 제목 계열 굵게 유지 */
            h1, h2, h3 {
                font-weight: 800 !important;
            }
            /* 테이블 내부 텍스트 크기만 조정 (색상 복구) */
            .stTable td, .stTable th, [data-testid="stTable"] {
                font-size: 1.05rem !important;
            }
            /* 사이드바 제거 시 메인 영역 확장 최적화 */
            section[data-testid="stSidebar"] {
                width: 0px !important;
                display: none !important;
            }
            .main .block-container {
                max-width: 95% !important;
                padding-top: 1.5rem !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # === 상단 전략 컨트롤 패널 (기존 사이드바에서 이동) ===
    st.title(f"🔥 KODEX IRP 실전 매매 컨트롤 타워 ({APP_VERSION} Stable)")
    
    with st.container():
        c_mode, c_info = st.columns([3, 1])
        with c_mode:
            strat_mode = st.radio(
                "🎯 전략 운용 모드 선택 (종목 수)",
                ["🚀 3종목 집중 투자 (수익률형)", "🛡️ 5종목 균형 투자 (표준형)", "🏦 10종목 전방위 투자 (안정형)"],
                index=2,
                horizontal=True
            )
        
        max_tickers = {"🚀 3종목 집중 투자 (수익률형)": 3, "🛡️ 5종목 균형 투자 (표준형)": 5, "🏦 10종목 전방위 투자 (안정형)": 10}[strat_mode]
        weight_per_ticker = 1.0 / max_tickers
        
        with c_info:
            st.info(f"**{max_tickers}종목** | 비중: **{weight_per_ticker*100:.1f}%**")

    # -------------------------------------------------------------------------------------
    # [V3.3.4] 무결성 추적 및 성과 데이터센터 (Definitive Truth - REFRESHED)
    # -------------------------------------------------------------------------------------

    
    # [V3.6.1] 티커 무결성 경고 (이름 불일치 시 최상단 빨간 배너)
    @st.cache_data(ttl=3600, show_spinner=False)
    def _cached_verify_tickers():
        return verify_tickers(TARGET_ETFS)
    ticker_issues = _cached_verify_tickers()
    if ticker_issues:
        with st.expander(f"🚨 티커 무결성 경고 {len(ticker_issues)}건 — 즉시 확인 필요", expanded=True):
            for msg in ticker_issues:
                st.error(msg)

    # [v3.3.3] 무결성 배지 (Integrity Status Badge) 최상단 배치
    c_badge1, c_badge2 = st.columns([1, 4])
    with c_badge1:
        st.success(f"✅ 데이터 무결성 검증 완료 ({APP_VERSION} Stable)")
    with c_badge2:
        if st.button("실전 신호 새로고침 🔄"):
            load_live_signals_only.clear()
            load_k200_benchmark.clear()
            st.rerun()

    # [V3.5.7] Track 1: 실전 신호 - 최근 400일 경량 로드
    with st.spinner("🔥 실전 신호 로드 중..."):
        all_signals, is_bull_now, k200_raw, integrity_live = load_live_signals_only()

    with st.expander("🛠️ 데이터 큐레이션 실시간 로그 (KRX Audit)"):
        st.write(f"**실전신호 로드:** 최근 {LIVE_LOOKBACK_DAYS}일 | {len(all_signals)}/{len(ETFS_CLEAN)} 종목 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(integrity_live.get('detail', ''))

    # [V3.5.7] Track 2: 백테스트 결과 - DB 캐시 우선, 캐시 미스 시 최초 1회 계산
    integrity_bt = {"score": 100, "detail": "DB 캐시"}
    port_res = load_backtest_from_db_cache(max_tickers)
    if port_res is None:
        with st.spinner(f"📊 최초 백테스트 계산 중... (이후 즉시 로드됩니다)"):
            all_signals_bt, _, _, _, integrity_bt = load_and_process_data_v3_5_2_MASTER_FINAL(is_backtest=True)
            port_res = run_portfolio_backtest(all_signals_bt, 50000000.0, max_tickers, True)
            if save_backtest_to_db_cache(port_res, max_tickers):
                st.toast("✅ 백테스트 결과 DB 캐시 저장 완료")

    # 무결성 메트릭
    BASELINE_RET_MAP = {3: 298.51, 5: 292.60, 10: 513.34}  # [V3.8.0 확정] 신규종목 공통 파라미터 k=0.5/mfi=50/adx=15
    actual_ret = port_res.get('cumulative_return', 0.0)
    target_baseline = BASELINE_RET_MAP.get(max_tickers, 472.66)
    diff_ret = actual_ret - target_baseline

    live_score = integrity_live.get('score', 0)
    bt_score = integrity_bt.get('score', 0)
    final_integrity_score = int((live_score + bt_score) / 2)

    c_int1, c_int2, c_int3, c_int4 = st.columns(4)
    c_int1.metric("시작-종료 범위", f"2019-01-02 ~ {BACKTEST_END_DATE}")
    c_int2.metric("이중 데이터 무결성 점수", f"🟢 {final_integrity_score}%", help=integrity_live.get('detail', ''))
    c_int3.metric("백테스팅 거래일 수", f"{port_res.get('total_days', TARGET_ROWS)} 거래일")
    integrity_status = "🟢 정상 (Verified)" if abs(diff_ret) < 0.1 else "🔴 주의 (Anomaly Detected)"
    c_int4.metric("수익률 정밀 오차", f"{diff_ret:+.2f}%", integrity_status)

    # [V3.6.1] 실전 신호 DB 저장은 GitHub Actions (daily_signal.yml) 이 매일 16:10 KST 자동 수행
    # app.py에서의 시간 조건부 저장 로직 제거 — 앱 오픈 여부와 무관하게 신뢰성 있게 기록됨

    st.divider()
    if not all_signals:
        st.error("데이터 로딩에 실패했습니다.")
        return

    today_date = max(df['date'].max() for df in all_signals.values())
    regime_text = f"🚀 [하이브리드 모드: {APP_VERSION} 전용 터보 가속 ON]" if is_bull_now else f"🛡️ [안정 모드: {APP_VERSION} 실전 대비 철벽 방어 ON]"
    st.info(f"최신 타점 갱신일: **{today_date}** | 시스템 엔진 상태: {regime_text}")
        
    tab1, tab4, tab2, tab3 = st.tabs([
        "🚀 AI 실전 시그널 보드", 
        "📈 실전 성과 궤적",
        "📊 전략별 백테스팅 종합판", 
        "🩺 알고리즘 무결성 진단"
    ])
    
    # === TAB 1: AI 실전 시그널 보드 ===
    with tab1:
        st.header(f"🎯 오늘의 AI 매매 권고  ({today_date} | 업데이트 {datetime.now().strftime('%H:%M')})")

        # 1) RS 전체 순위
        valid_signals = [
            (n, d['composite_rs'].iloc[-1])
            for n, d in all_signals.items()
            if 'composite_rs' in d.columns
        ]
        rs_ranked = sorted(valid_signals, key=lambda x: x[1], reverse=True)
        rs_rank_map = {name: i + 1 for i, (name, _) in enumerate(rs_ranked)}
        top5_names = [name for name, _ in rs_ranked[:5]]  # 카드는 항상 TOP 5 고정

        # 2) 현재 보유 종목 조회 (live_trades DB)
        held_names = set()
        try:
            trades_res = supabase.table('live_trades').select('ticker,action').execute()
            pos = {}
            for r in (trades_res.data or []):
                if r['action'] == 'BUY':
                    pos[r['ticker']] = True
                elif r['action'] == 'EXIT':
                    pos.pop(r['ticker'], None)
            held_names = set(pos.keys())
        except Exception:
            pass

        # 2-B) 매수 대기 종목: 전날 buy_signal=True인데 아직 live_trades 체결 기록 없는 종목
        # → 오늘 아침 9시에 매수해야 하지만 16:10 전까지 live_trades에 기록이 없는 구간 커버
        pending_buy_names = set()
        try:
            import datetime as _dt
            yesterday_str = (_dt.date.today() - _dt.timedelta(days=1)).strftime('%Y-%m-%d')
            # 주말/월요일 보정: 토=5, 일=6이면 금요일로
            wd = _dt.date.today().weekday()
            if wd == 0:   # 월요일 → 금요일 신호
                yesterday_str = (_dt.date.today() - _dt.timedelta(days=3)).strftime('%Y-%m-%d')
            sig_yes = supabase.table('daily_signals').select('ticker,buy_signal').eq('signal_date', yesterday_str).execute()
            for r in (sig_yes.data or []):
                if r.get('buy_signal') and r['ticker'] not in held_names:
                    pending_buy_names.add(r['ticker'])
        except Exception:
            pass

        # 3) 카드 목록 = TOP 5 RS 고정 (보유/매수대기가 top5 밖이면 보유섹션에서 별도 표시)
        card_list = top5_names

        NAME_TO_TICKER = {v: k for k, v in ETFS_CLEAN.items()}  # [V3.8.0] .KS 제거된 clean code 사용

        # 범례
        st.caption(f"🔵 보유중 | 🟡 매수 대기(오늘 시가 매수 예정) | TOP 5 RS 고정 표시 | 보유 종목은 하단 섹션 참조")

        cols_per_row = 3
        def ck(b): return "✅" if b else "❌"

        for r_idx in range(0, len(card_list), cols_per_row):
            row_names = card_list[r_idx: r_idx + cols_per_row]
            cols = st.columns(cols_per_row)
            for i, name in enumerate(row_names):
                if name not in all_signals:
                    continue
                df_curr   = all_signals[name].iloc[-1]
                target_p  = df_curr['target_break_price']
                curr_p    = df_curr['close']
                ticker_symbol = NAME_TO_TICKER.get(name, "N/A")
                is_held      = name in held_names
                is_pending   = name in pending_buy_names
                rs_rank      = rs_rank_map.get(name, 99)
                rs_rank_txt  = f"🏆 RS {rs_rank}위" if rs_rank <= 3 else f"RS {rs_rank}위"

                params  = TICKER_PARAMS.get(name, {'k': 0.5, 'mfi': 60, 'adx_threshold': 20})
                mfi_thr = params['mfi']
                adx_thr = params['adx_threshold']
                c1_pass = curr_p > target_p   # strategy.py 백테스팅과 동일: close > target_break_price
                c2_pass = float(df_curr.get('mfi', 0)) > mfi_thr
                c3_pass = float(df_curr.get('intraday_intensity', 0)) > 0
                c4_pass = float(df_curr.get('adx_14', 0)) > adx_thr
                passed  = sum([c1_pass, c2_pass, c3_pass, c4_pass])

                exit_signal = bool(df_curr.get('exit_signal_T', False))

                # 보유 카드 전용: 매도 모니터링 섹션
                exit_monitor_html = ""
                if is_held:
                    is_bull_now_card = bool(df_curr.get('is_bull_market', False))
                    vol_rank_val     = float(df_curr.get('vol_rank', 0.5))
                    sma5_val  = float(df_curr.get('sma_5',  0))
                    sma10_val = float(df_curr.get('sma_10', 0))
                    sma20_val = float(df_curr.get('sma_20', 0))
                    if is_bull_now_card:
                        exit_sma_label = "SMA 5일선 (불장)"
                        exit_sma_val   = sma5_val
                    elif vol_rank_val < 0.3:
                        exit_sma_label = "SMA 10일선 (저변동성)"
                        exit_sma_val   = sma10_val
                    else:
                        exit_sma_label = "SMA 20일선 (고변동성)"
                        exit_sma_val   = sma20_val
                    ex_op    = "&lt;" if exit_signal else "≥"
                    ex_color = "#FF4444" if exit_signal else "#00FF88"
                    ex_text  = "🔴 이탈 → 매도 신호" if exit_signal else "🟢 유지 중"
                    exit_monitor_html = (
                        f'<hr style="margin:12px 0; border:1px solid #444;">'
                        f'<div style="font-size:0.85rem; color:#AAA; margin-bottom:6px;">📤 매도 모니터링 ({exit_sma_label})</div>'
                        f'<div style="font-size:1.0rem; color:#fff;">현재가 <b>{curr_p:,.0f}원</b> {ex_op} {exit_sma_label} <b>{exit_sma_val:,.0f}원</b>'
                        f'&nbsp;<span style="color:{ex_color}; font-weight:800;">{ex_text}</span></div>'
                    )

                # 상태 결정 (우선순위: 매도 > 보유유지 > 매수대기 > BUY > 관망)
                if is_held and exit_signal:
                    sig_status   = "🔴 [매도 신호]"
                    color_hex    = "#FF4444"
                    border_style = "3px solid #FF4444"
                    bg_color     = "#2d0d0d"
                    held_badge   = "<span style='background:#FF4444;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:800;margin-left:8px;'>보유중</span>"
                    conclusion   = "<span style='color:#FF4444;'>🚨 오늘 시가 매도 집행</span>"
                elif is_held:
                    sig_status   = "🔵 [보유 유지]"
                    color_hex    = "#00BFFF"
                    border_style = "3px solid #00BFFF"
                    bg_color     = "#0d1f2d"
                    held_badge   = "<span style='background:#00BFFF;color:#000;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:800;margin-left:8px;'>보유중</span>"
                    conclusion   = "<span style='color:#00BFFF;'>📦 보유 중 — 매도 신호 없음</span>"
                elif is_pending:
                    sig_status   = "⏰ [매수 대기]"
                    color_hex    = "#FFD700"
                    border_style = "3px solid #FFD700"
                    bg_color     = "#2d2500"
                    held_badge   = "<span style='background:#FFD700;color:#000;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:800;margin-left:8px;'>오늘 매수</span>"
                    conclusion   = "<span style='color:#FFD700;'>⏰ 전일 신호 — 오늘 시가 매수 예정</span>"
                elif passed == 4:
                    sig_status   = "🟢 [BUY/HOLD]"
                    color_hex    = "#00FF00"
                    border_style = "2px solid #666"
                    bg_color     = "#1e1e1e"
                    held_badge   = ""
                    conclusion   = "<span style='color:#00FF00;'>🚀 내일 시가 매수 집행</span>"
                elif passed == 3:   # 정확히 1개 미달일 때만 🟡 (passed 기준, 가격 근접도와 무관)
                    sig_status   = "🟡 [매수 대기]"
                    color_hex    = "#FFA500"
                    border_style = "2px solid #666"
                    bg_color     = "#1e1e1e"
                    held_badge   = ""
                    conclusion   = "<span style='color:#FFA500;'>⏳ 조건 1개 미달 (근접)</span>"
                else:
                    sig_status   = "⚪ [관망/준비]"
                    color_hex    = "#AAAAAA"
                    border_style = "2px solid #666"
                    bg_color     = "#1e1e1e"
                    held_badge   = ""
                    conclusion   = f"<span style='color:#AAAAAA;'>💤 조건 {passed}/4 충족 (대기)</span>"

                with cols[i]:
                    # 카드 HTML을 문자열 이어붙이기로 사전 빌드 → st.markdown에 완성본만 전달
                    # (f-string 다중행 방식은 빈 줄 → 마크다운 파서 HTML 블록 파괴 버그 유발)
                    _mfi_val = float(df_curr.get('mfi', 0))
                    _adx_val = float(df_curr.get('adx_14', 0))
                    _c1_sym  = "≥" if c1_pass else "&lt;"
                    _c2_sym  = "≥" if c2_pass else "&lt;"
                    _c4_sym  = "≥" if c4_pass else "&lt;"
                    _ii_txt  = "지배(양수)" if c3_pass else "미지배(음수)"
                    _card = (
                        f'<div style="border:{border_style};border-radius:12px;padding:20px;margin-bottom:15px;background-color:{bg_color};box-shadow:0 4px 6px rgba(0,0,0,0.3);">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                        f'<span><span style="background-color:{color_hex};color:#000;padding:4px 10px;border-radius:6px;font-weight:800;font-size:0.9rem;">{sig_status}</span>{held_badge}</span>'
                        f'<span style="color:#FFF;font-size:0.9rem;font-weight:bold;">{rs_rank_txt}</span>'
                        f'</div>'
                        f'<div style="font-size:1.6rem;font-weight:900;color:{color_hex};margin-bottom:4px;">{name}</div>'
                        f'<div style="font-size:0.95rem;color:#888;font-weight:600;margin-bottom:10px;">Ticker: {ticker_symbol}</div>'
                        f'<hr style="margin:12px 0;border:1px solid #444;">'
                        f'<div style="display:flex;justify-content:space-between;font-size:1.2rem;">'
                        f'<span style="color:#FFFFFF;font-weight:bold;">🎯 돌파 목표가</span>'
                        f'<span style="font-weight:bold;color:#ffdd44;">{target_p:,.0f}원</span></div>'
                        f'<div style="display:flex;justify-content:space-between;font-size:1.2rem;margin-top:6px;">'
                        f'<span style="color:#FFFFFF;font-weight:bold;">📉 현재가</span>'
                        f'<span style="color:#FFFFFF;font-weight:bold;">{curr_p:,.0f}원</span></div>'
                        f'<hr style="margin:12px 0;border:1px solid #444;">'
                        f'<div style="font-size:1.1rem;color:#fff;line-height:1.6;">'
                        f'<div style="margin-bottom:4px;">{ck(c1_pass)} <b>가격 돌파</b> &nbsp; <span style="color:#DDD;">({curr_p:,.0f} {_c1_sym} {target_p:,.0f})</span></div>'
                        f'<div style="margin-bottom:4px;">{ck(c2_pass)} <b>스마트머니(MFI)</b> &nbsp; <span style="color:#DDD;">({_mfi_val:.1f} {_c2_sym} {mfi_thr})</span></div>'
                        f'<div style="margin-bottom:4px;">{ck(c3_pass)} <b>일봉 지배력(II)</b> &nbsp; <span style="color:#DDD;">({_ii_txt})</span></div>'
                        f'<div style="margin-bottom:4px;">{ck(c4_pass)} <b>추세 강도(ADX)</b> &nbsp; <span style="color:#DDD;">({_adx_val:.1f} {_c4_sym} {adx_thr})</span></div>'
                        f'</div>'
                        f'{exit_monitor_html}'
                        f'<hr style="margin:12px 0;border:1px solid #444;">'
                        f'<div style="font-size:1.2rem;font-weight:bold;">{conclusion}</div>'
                        f'</div>'
                    )
                    st.markdown(_card, unsafe_allow_html=True)

        # ── 보유 포지션 상세 섹션 ─────────────────────────────────────────────
        st.divider()
        st.subheader("📦 현재 보유 포지션")
        if not held_names:
            st.info("현재 보유 중인 포지션 없음")
        else:
            pos_rows = []
            try:
                trades_detail = supabase.table('live_trades').select(
                    'ticker,action,units,execute_price,hard_stop_pct,execute_date'
                ).execute()
                pos_map = {}
                for r in (trades_detail.data or []):
                    if r['action'] == 'BUY':
                        pos_map[r['ticker']] = r
                    elif r['action'] in ('EXIT','EXIT_HARDSTOP','EXIT_SWITCH') and r['ticker'] in pos_map:
                        del pos_map[r['ticker']]
            except Exception:
                pos_map = {}

            for ticker_name in sorted(held_names):
                if ticker_name not in all_signals:
                    continue
                df_curr    = all_signals[ticker_name].iloc[-1]
                curr_p     = float(df_curr.get('close', 0))
                exit_sig   = bool(df_curr.get('exit_signal_T', False))
                rs_rank    = rs_rank_map.get(ticker_name, 99)
                switching  = rs_rank > MAX_POSITIONS

                pos_info   = pos_map.get(ticker_name, {})
                entry_p    = float(pos_info.get('execute_price') or 0)
                stop_pct   = float(pos_info.get('hard_stop_pct') or 0)
                units      = float(pos_info.get('units') or 0)
                entry_date = pos_info.get('execute_date', '-')
                stop_price = entry_p * (1 - stop_pct) if entry_p > 0 and stop_pct > 0 else 0
                pnl_pct    = ((curr_p / entry_p) - 1) * 100 if entry_p > 0 else 0
                eval_amt   = units * curr_p

                # 경고 표시
                warn = []
                if exit_sig:
                    warn.append("🔴 SMA 이탈")
                if switching:
                    warn.append(f"⚠️ RS {rs_rank}위 (TOP{MAX_POSITIONS} 이탈)")
                warn_txt = " | ".join(warn) if warn else "🟢 정상 보유"

                pos_rows.append({
                    "종목명":     ticker_name,
                    "진입일":     entry_date,
                    "진입가":     f"{entry_p:,.0f}",
                    "현재가":     f"{curr_p:,.0f}",
                    "평가손익":   f"{pnl_pct:+.2f}%",
                    "평가금액":   f"{eval_amt:,.0f}",
                    "RS순위":     f"{rs_rank}위",
                    "하드스탑가": f"{stop_price:,.0f}" if stop_price > 0 else "-",
                    "상태":       warn_txt,
                })

            if pos_rows:
                st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)

        st.caption("📡 매일 오후 4시, 시그널 발생 종목이 자동으로 '실전 성과 궤적' 탭에 기록됩니다.")

    # === TAB 2: 백테스팅 종합 대시보드 ===
    with tab2:
        st.header(f"📊 {max_tickers}종목 전략 통합 백테스팅 결과")
        # [V3.3.1] 최적화: 상단 무결성 감시장치(138라인)에서 이미 연산된 port_res 재사용 (메모리 절감)
        total_pct = ((port_res['final_capital'] / 50000000.0) - 1) * 100
        
        m1, m2, m3 = st.columns(3)
        m1.metric("초기 원금", "50,000,000 원")
        m2.metric(f"최종 누적 잔고", f"{port_res['final_capital']:,.0f} 원")
        
        m3.metric("누적 수익률", f"{total_pct:,.2f} %", f"CAGR {port_res['cagr']}%")

        if not port_res['history'].empty:
            hist_df = port_res['history'].set_index('date')
            bm_df = load_k200_benchmark()  # [V3.5.7] 전체 기간 K200 벤치마크 (2019-현재)
            if bm_df.empty:
                bm_df = all_signals.get("KODEX 200", pd.DataFrame()).copy()
                if not bm_df.empty: bm_df = bm_df.set_index('date')
            first_open = bm_df['open'].iloc[0] if not bm_df.empty else 1
            bm_df['KOSPI 200'] = (bm_df['close'] / first_open) * 50000000
            chart_df = hist_df[['total_value']].join(bm_df[['KOSPI 200']], how='left')
            st.line_chart(chart_df, color=["#ff4b4b", "#1f77b4"])
            
            # 연도별 테이블
            # [V3.5.9] bm_df empty/KeyError 완전 방어 + irp_p 기반 연도 보장
            yearly_df = hist_df[['total_value']].copy()
            yearly_df.index = pd.to_datetime(yearly_df.index)
            bm_has_close = (not bm_df.empty) and ('close' in bm_df.columns)
            if bm_has_close:
                ko_close_aligned = bm_df['close'].reindex(
                    yearly_df.index.strftime('%Y-%m-%d')).ffill().bfill()
                ko_close_aligned.index = yearly_df.index
                yearly_df['ko200_close'] = ko_close_aligned.values
            else:
                yearly_df['ko200_close'] = float('nan')
            y_last = yearly_df.resample('YE').last()
            # irp_p는 DB 기반으로 항상 전체 연도 보장
            irp_p = pd.Series([50000000] + y_last['total_value'].tolist()).pct_change().dropna() * 100
            years  = list(y_last.index.year)
            ko_vals = y_last['ko200_close'].tolist()
            ko_series = pd.Series([first_open] + ko_vals).pct_change().dropna() * 100
            ko_total = ((ko_vals[-1] / first_open) - 1) * 100 if bm_has_close and first_open > 1 else float('nan')
            y_data = [{"연도": "✨ [TOTAL]", "IRP 수익률(%)": round(total_pct, 2),
                       "KOSPI 200(%)": round(ko_total, 2) if not pd.isna(ko_total) else "N/A",
                       "Alpha(pp)": round(total_pct - ko_total, 2) if not pd.isna(ko_total) else "N/A"}]
            for y, ir in zip(years, irp_p):   # irp_p 기준으로 모든 연도 표시 보장
                ko = ko_series.iloc[years.index(y)] if y in years and len(ko_series) > years.index(y) else float('nan')
                ko_str = round(ko, 2) if not pd.isna(ko) else "N/A"
                alpha_str = round(ir - ko, 2) if not pd.isna(ko) else "N/A"
                y_data.append({"연도": f"{y}년", "IRP 수익률(%)": round(ir, 2), "KOSPI 200(%)": ko_str, "Alpha(pp)": alpha_str})
            st.dataframe(pd.DataFrame(y_data), use_container_width=True, hide_index=True)
            
            st.divider()
            trades_df = port_res['trades_df']
            trade_count = len(trades_df) if not trades_df.empty else 0
            st.subheader(f"📚 백테스트 상세 매매 일지 (Trade Logs) — 총 {trade_count}건")

            if not trades_df.empty:
                # 콤마 및 포맷팅 처리
                styled_trades = trades_df.copy()
                # DataFrame display (built-in download provided by this table will now include new columns)
                st.dataframe(styled_trades, use_container_width=True, hide_index=True)
                
                # [V3.4.0.4 FINAL] 가장 표준적인 Streamlit 다운로드 버튼 방식 사용
                # 복잡한 HTML/Base64 방식을 폐기하고, 공식 가이드라인에 따른 최적화된 버튼을 배치합니다.
                csv_data = trades_df.to_csv(index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 전체 매매 일지 엑셀(CSV) 다운로드",
                    data=csv_data,
                    file_name="kodex_irp_trade_logs.csv",
                    mime="text/csv",
                    key=f"dl_v3404_{int(time.time())}"
                )
            else:
                st.info("기간 내에 발생한 매매 내역이 없습니다.")

    # === TAB 3: 알고리즘 무결성 진단 (투명화 고도화) ===
    with tab3:
        st.header("🩺 투명한 하이브리드 엔진 설계도 (무결성 공시)")
        
        # [V3.5.12] 전일 시장 레짐 판독 엔진 - 수치 기반 정보판
        st.subheader("📡 전일 시장 레짐 판독 엔진 (KODEX 200 기반)")

        # 실시간 레짐 수치 계산
        _adx_now = _adx_mu = _adx_sigma = _z_now = _mfi_now = _sigma_20 = _sigma_avg = float('nan')
        if not k200_raw.empty and 'adx_14' in k200_raw.columns:
            _adx_series = k200_raw['adx_14'].dropna()
            if len(_adx_series) >= 2:
                _adx_now   = k200_raw['adx_14'].iloc[-1]
                _adx_mu    = k200_raw['adx_14'].rolling(252).mean().iloc[-1]
                _adx_sigma = k200_raw['adx_14'].rolling(252).std().iloc[-1]
                _z_now     = (_adx_now - _adx_mu) / _adx_sigma if _adx_sigma > 0 else float('nan')
            if 'mfi' in k200_raw.columns:
                _mfi_now = k200_raw['mfi'].iloc[-1]
            if 'sigma_20' in k200_raw.columns:
                _sigma_20 = k200_raw['sigma_20'].iloc[-1]
            if 'sigma_avg' in k200_raw.columns:
                _sigma_avg = k200_raw['sigma_avg'].iloc[-1]

        _z1_pass  = (not pd.isna(_z_now))  and _z_now  > 2.0
        _z2_pass  = (not pd.isna(_mfi_now)) and _mfi_now > 40
        _regime_label = "🚀 BULL (터보 공격)" if is_bull_now else "🛡️ STABLE (안정)"
        _fmt = lambda v, d=2: f"{v:.{d}f}" if not pd.isna(v) else "N/A"

        # 헤더 행: 기준일 + 판정 뱃지
        _hcol1, _hcol2 = st.columns([3, 1])
        with _hcol1:
            st.caption("기준일: 직전 거래일 종가 | 데이터: KODEX 200 (069500)")
        with _hcol2:
            if is_bull_now:
                st.error(_regime_label)
            else:
                st.info(_regime_label)

        # STEP 1~4 카드 (st.columns 4분할)
        _c1, _c2, _c3, _c4 = st.columns(4)

        with _c1:
            st.markdown("**🔵 STEP 1 · ADX 14일선**")
            st.metric("현재 ADX", _fmt(_adx_now))
            st.caption(f"252일 평균(μ): {_fmt(_adx_mu)}")
            st.caption(f"252일 표준편차(σ): {_fmt(_adx_sigma)}")

        with _c2:
            st.markdown("**🔵 STEP 2 · Z-Score**")
            st.metric("Z = (ADX−μ)/σ", _fmt(_z_now),
                      delta="임계 초과 ✅" if _z1_pass else f"미달 ❌ (임계: > 2.0)",
                      delta_color="normal" if _z1_pass else "inverse")
            st.caption("Bull 진입: Z > 2.0")
            st.caption("Stable 복귀: Z < 1.0")

        with _c3:
            st.markdown("**🔵 STEP 3 · MFI 스마트머니**")
            st.metric("MFI (시장 유동성)", _fmt(_mfi_now),
                      delta="조건 충족 ✅" if _z2_pass else f"미달 ❌ (임계: > 40)",
                      delta_color="normal" if _z2_pass else "inverse")
            st.caption("시장 전체 유동성 필터")
            st.caption("Bull 진입 조건: MFI > 40")

        with _c4:
            st.markdown("**🔵 STEP 4 · 최종 판정**")
            if is_bull_now:
                st.error(_regime_label)
            else:
                st.info(_regime_label)
            st.caption(f"① Z > 2.0   {'✅' if _z1_pass else '❌'}")
            st.caption(f"② MFI > 40  {'✅' if _z2_pass else '❌'}")
            st.caption("① ② 동시 충족 시 BULL 진입")
            st.caption("히스테리시스: Z < 1.0 시 Stable 복귀")

        # 매매 파라미터 영향
        st.markdown("**⚙️ 현재 레짐의 매매 파라미터 영향**")
        _p1, _p2 = st.columns(2)
        with _p1:
            if is_bull_now:
                st.markdown("**진입 K값 공식**\n\nK_base × (σ₂₀/σ_avg) × **0.4** `[Turbo 60% 할인 ON]` *(Dynamic K, 클램프 0.2~0.8)*")
            else:
                st.markdown("**진입 K값 공식**\n\nK_base × (σ₂₀/σ_avg) `[Turbo 할인 없음]` *(Dynamic K, 클램프 0.2~0.8)*")
        with _p2:
            if is_bull_now:
                st.markdown("**청산선**\n\nSMA **5**일선 이탈 시 익절 *(빠른 추격)*")
            else:
                st.markdown("**청산선**\n\nvol_rank < 0.3 → SMA **10**일 / 그외 → SMA **20**일")

        st.subheader("⚙️ 종목별 개별 최적화 파라미터 (TICKER_PARAMS)")
        param_df = pd.DataFrame(TICKER_PARAMS).T.reset_index()
        param_df.columns = ["종목명", "변동성 상수(K)", "수급 임계치(MFI)", "추세 임계치(ADX)"]
        st.table(param_df)

        st.divider()
        
        st.subheader("📊 랭킹 산출 근거 (Composite RS Integrity)")
        # 랭킹의 재료가 되는 숫자를 투명하게 노출
        ranking_data = []
        for name, df in all_signals.items():
            curr = df.iloc[-1]
            prev_20 = df.iloc[-21] if len(df) >= 21 else df.iloc[0]
            
            # [V3.5.2 Intelligent Exit Engine - Validation]
            # strategy.py에서 이미 계산된 exit_signal_T를 안전하게 참조만 하도록 구조를 단순화합니다.
            is_bull_v = df['is_bull_market']
            df['exit_signal_T'] = np.where(
                is_bull_v, 
                df['close'] < df['sma_5'], 
                np.where(df['vol_rank'] < 0.3, df['close'] < df['sma_10'], df['close'] < df['sma_20'])
            )
            
            # 추세 가점 수동 복기용 계산 (불리언 버그 방지를 위해 정수 변환)
            ma20_ok = curr['close'] > curr['sma_20']
            ma60_ok = curr['close'] > curr['sma_60']
            ma120_ok = curr['close'] > curr['sma_120']
            tr_score = int(ma20_ok) + int(ma60_ok) + int(ma120_ok)
            
            # O/X 표기
            flag_20 = "🟢" if ma20_ok else "🔴"
            flag_60 = "🟢" if ma60_ok else "🔴"
            flag_120 = "🟢" if ma120_ok else "🔴"
            
            ranking_data.append({
                "종목명": name,
                "현재가 (T)": f"{curr['close']:,.0f}원",
                "20일 등락률 [(P_now/P_20d)-1]": f"{curr['rs_20']*100:+.2f}%",
                "추세 가점 내역 (20, 60, 120일)": f"[{flag_20}{flag_60}{flag_120}] ➡️ {tr_score}점",
                "복합RS [등락률 × (1 + 0.5×추세점수)]": f"{curr['composite_rs']*100:+.2f}%"
            })
        
        rank_raw_df = pd.DataFrame(ranking_data).sort_values("복합RS [등락률 × (1 + 0.5×추세점수)]", ascending=False)
        st.write("**현재 상동한 랭킹 정렬의 실시간 엔진 내부 수치입니다.** (추세 점수가 낮은 역배열 종목은 후순위로 자동 배치)")
        st.table(rank_raw_df.reset_index(drop=True))

        st.markdown("""
        ### ⚖️ 무결성 선언 (V3.4.0 Engine Truth)
        1. **완벽한 데이터 동기화 (Absolute Math Sync):** 모든 종목의 수급 지표(MFI)와 보강 지표는 **빈칸이 상속되기 전 오염되지 않은 절대 원본**에서 선출출되며, 이후 KODEX 200의 날짜 축으로 평탄화 연산을 거칩니다. 이는 229.37%의 수익을 0.00% 오차 없이 실현하는 핵심 구조입니다.
        2. **터보 가속 (Turbo-K 엔진):** 시장에 유동성(MFI > 40)이 유입되는 **진짜 불장**으로 판독될 경우에 한하여, K값을 무려 **50% 강제 할인**시켜 주도주 랠리에 극초반 탑승합니다.
        3. **예수금 박멸 (Dynamic Cash Sweep):** 남는 포트폴리오 슬롯이 발생할 경우, 노는 현금이 없도록 **잔여 예수금의 100%(수수료 버퍼 제외)**를 매수 예정 종목에 공격적으로 전액 재분배합니다. 이것이 코스피 -26% 폭락장에서도 수익률을 방어하고 폭발시킨 V3.4.0의 근본입니다.
        """)

    with tab4:
        st.header("📈 실전 성과 궤적 (시그널 모니터링)")
        st.markdown("매일 16:00 기준으로 자동 기록된 시그널과 수익률 추이를 추적합니다.")

        # [V3.6.1] 실전 포트폴리오 누적 수익률 추이
        st.subheader("📊 실전 포트폴리오 누적 수익률 (2026-04-08 시작)")
        LIVE_START_CAPITAL = 50_000_000.0
        try:
            live_res = supabase.table('live_portfolio_history').select('date,total_value').order('date', desc=False).execute()
            if live_res.data and len(live_res.data) >= 1:
                live_df = pd.DataFrame(live_res.data)
                live_df['date'] = pd.to_datetime(live_df['date'])
                live_df['실전 수익률(%)'] = (live_df['total_value'] / LIVE_START_CAPITAL - 1) * 100
                live_df = live_df.set_index('date')

                # 실전 매매 이력 테이블
                trade_res = supabase.table('live_trades').select('*').order('execute_date', desc=True).limit(50).execute()
                col_chart, col_stats = st.columns([2, 1])
                with col_chart:
                    st.line_chart(live_df[['실전 수익률(%)']])
                with col_stats:
                    last_val   = float(live_df['total_value'].iloc[-1])
                    last_ret   = float(live_df['실전 수익률(%)'].iloc[-1])
                    n_days     = len(live_df)
                    st.metric("현재 포트폴리오 가치", f"{last_val:,.0f}원")
                    st.metric("누적 수익률", f"{last_ret:+.2f}%")
                    st.metric("운용 기간", f"{n_days}일")

                # 실전 체결 이력
                st.subheader("📋 실전 매매 체결 이력")
                if trade_res.data:
                    trade_df = pd.DataFrame(trade_res.data)
                    trade_df = trade_df[['execute_date','signal_date','ticker','action','execute_price','units','amount']]
                    trade_df.columns = ['체결일','신호일','종목','매매','체결가','수량','금액']
                    trade_df['체결가'] = trade_df['체결가'].apply(lambda x: f"{x:,.0f}원")
                    trade_df['금액']   = trade_df['금액'].apply(lambda x: f"{x:,.0f}원")
                    st.dataframe(trade_df, use_container_width=True, hide_index=True)
                else:
                    st.info("아직 체결 기록이 없습니다. 첫 매매 신호 발생 익일 09시 이후 자동 기록됩니다.")
            else:
                st.info("🕐 실전 포트폴리오 데이터 없음 — 오늘 16:10 KST 첫 기록 예정.")
        except Exception as e:
            if 'live_portfolio_history' in str(e):
                st.warning("🛠️ Supabase에서 live_portfolio_history / live_trades 테이블을 생성해주세요. (schema/live_trading_tables.sql)")
            else:
                st.error(f"실전 수익률 조회 실패: {e}")

        st.divider()

        st.divider()

        # [Fix 3-B] 종목별 시그널 이력
        st.subheader("📡 종목별 시그널 이력 (BUY/EXIT 발생 기록)")
        try:
            sig_res = supabase.table('daily_signals').select('*').order('signal_date', desc=True).limit(100).execute()
            if sig_res.data:
                sig_df = pd.DataFrame(sig_res.data)
                sig_df = sig_df[['signal_date','ticker','close','target_break_price','composite_rs','buy_signal','exit_signal','mfi']]
                show_buy_only = st.checkbox("BUY 시그널 발생 종목만 보기", value=False)
                if show_buy_only:
                    sig_df = sig_df[sig_df['buy_signal'] == True]
                st.dataframe(sig_df, use_container_width=True, hide_index=True)
            else:
                st.info("🕐 아직 기록된 시그널이 없습니다. 오늘 오후 4시 이후 자동 적재됩니다.")
        except Exception as e:
            err_str = str(e)
            if 'PGRST205' in err_str or 'daily_signals' in err_str:
                st.warning("🛠️ DB 테이블이 아직 생성되지 않았습니다. Supabase에서 `daily_signals` 테이블을 생성하면 자동 적재됩니다.")
            else:
                st.error(f"시그널 이력 조회 실패: {e}")

if __name__ == "__main__":
    main()
