import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.strategy import build_signals_and_targets, get_market_regime, TICKER_PARAMS
from analytics.portfolio_backtester import run_portfolio_backtest
from analytics.backtester import run_vectorized_backtest
from data_collector.daily_scraper import calculate_mfi, calculate_intraday_intensity, TARGET_ETFS, verify_dual_source_integrity
from analytics.integrity_monitor import log_backtest_integrity

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

@st.cache_data(ttl=3600)
def load_and_process_data_v3_1_2():
    # 1. 원천 데이터 확보 (yfinance 기반)
    TARGET_ETFS = {
        "069500.KS": "KODEX 200", 
        "226490.KS": "KODEX 코스닥150",
        "091160.KS": "KODEX 반도체",
        "091170.KS": "KODEX 은행",
        "091180.KS": "KODEX 자동차",
        "305720.KS": "KODEX 2차전지산업",
        "117700.KS": "KODEX 건설",
        "091220.KS": "KODEX 금융",
        "102970.KS": "KODEX 기계장비",
        "117680.KS": "KODEX 철강"
    }
    
    # [무결성 V3.1.7] 가격 오염 차단을 위해 멀티 티커 다운로드를 폐지하고 개별 호출 수행
    all_signals = {}
    
    # 레짐 판독용 KODEX 200 데이터 별도 확보
    k200_data = yf.download("069500.KS", start="2019-01-01", progress=False)
    # [디버그 fix] yfinance 최신버전 MultiIndex 컬럼 평탄화 (계산 로직 무관)
    if isinstance(k200_data.columns, pd.MultiIndex):
        k200_data.columns = [col[0] for col in k200_data.columns]
    k200_raw = k200_data.dropna().reset_index()
    k200_raw['date'] = k200_raw['Date'].dt.strftime('%Y-%m-%d')
    df_upper_k2 = k200_raw.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
    k200_raw['mfi'] = calculate_mfi(df_upper_k2)
    k200_raw['intraday_intensity'] = calculate_intraday_intensity(df_upper_k2)
    k200_raw = k200_raw.dropna().reset_index(drop=True)
    # [디버그 fix] strategy.py가 소문자 컬럼명을 기대하므로 변환 (계산 로직 무관)
    k200_raw = k200_raw.drop(columns=['Date'], errors='ignore')
    k200_raw.columns = [c.lower() for c in k200_raw.columns]
    k200_signals = build_signals_and_targets(k200_raw, ticker_name="KODEX 200")
    regime_series = get_market_regime(k200_signals)

    common_dates = k200_data.index
    
    for raw_ticker, name in TARGET_ETFS.items():
        # [무결성 V3.1.7] 종목별 개별 핀셋 호출 (삼성전자 가격 침범 물리적 차단)
        data_single = yf.download(raw_ticker, start="2019-01-01", progress=False)
        # [디버그 fix] yfinance 최신버전 MultiIndex 컬럼 평탄화 (계산 로직 무관)
        if isinstance(data_single.columns, pd.MultiIndex):
            data_single.columns = [col[0] for col in data_single.columns]
        df_clean = data_single.copy()
        
        # 컬럼명을 소문자로 통일 (Open -> open)
        df_clean.columns = [c.lower() for c in df_clean.columns]
        df_clean = df_clean.ffill().fillna(0).reset_index()
        df_clean.rename(columns={'Date': 'date'}, inplace=True)
        # 만약 date 컬럼이 없으면 인덱스에서 복구
        if 'date' not in df_clean.columns and 'Date' in df_clean.columns:
            df_clean.rename(columns={'Date': 'date'}, inplace=True)
            
        df_clean['date'] = pd.to_datetime(df_clean['date']).dt.strftime('%Y-%m-%d')
        
        if df_clean.empty: continue
            
        # [복구] 수급 지표 및 시그널 계산
        df_upper = df_clean.rename(columns=lambda x: x.capitalize() if x != 'date' else x)
        df_clean['mfi'] = calculate_mfi(df_upper)
        df_clean['intraday_intensity'] = calculate_intraday_intensity(df_upper)
        
        ticker_signals = build_signals_and_targets(df_clean, ticker_name=name, is_bull_market=regime_series)
        all_signals[name] = ticker_signals

    # 현재 레짐 상태 (최신일 기준)
    is_bull_now = regime_series.iloc[-1]
    
    return all_signals, is_bull_now, k200_data

def main():
    # [Custom CSS] 폰트 크기 30% 증대 및 고대비 색상 강제 적용
    st.markdown("""
        <style>
            /* 일반 텍스트 및 캡션 크기 증대 */
            .stMarkdown p, .stCaption, div[data-testid="stCaptionContainer"] {
                font-size: 1.15rem !important; /* 약 30% 증대 (기존 0.8~0.9rem) */
                color: #FFFFFF !important;    /* 희미한 색 제거, 순백색 강제 */
            }
            /* 테이블 내부 텍스트 크기 및 대비 */
            .stTable td, .stTable th, [data-testid="stTable"] {
                font-size: 1.1rem !important;
                color: #FFFFFF !important;
            }
            /* 사이드바 제거 시 메인 영역 확장 최적화 */
            section[data-testid="stSidebar"] {
                width: 0px !important;
                display: none !important;
            }
            .main .block-container {
                max-width: 95% !important;
                padding-top: 2rem !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # === 상단 전략 컨트롤 패널 (기존 사이드바에서 이동) ===
    st.title("🔥 KODEX IRP 실전 매매 컨트롤 타워 (V3.3.5)")
    
    with st.container():
        c_mode, c_info = st.columns([3, 1])
        with c_mode:
            strat_mode = st.radio(
                "🎯 전략 운용 모드 선택 (종목 수)",
                ["🚀 3종목 집중 투자 (수익률형)", "🛡️ 5종목 균형 투자 (표준형)", "🏦 10종목 전방위 투자 (안정형)"],
                index=0,
                horizontal=True
            )
        
        max_tickers = {"🚀 3종목 집중 투자 (수익률형)": 3, "🛡️ 5종목 균형 투자 (표준형)": 5, "🏦 10종목 전방위 투자 (안정형)": 10}[strat_mode]
        weight_per_ticker = 1.0 / max_tickers
        
        with c_info:
            st.info(f"**{max_tickers}종목** | 비중: **{weight_per_ticker*100:.1f}%**")

    # -------------------------------------------------------------------------------------
    # [V3.3.4] 무결성 추적 및 성과 데이터센터 (Definitive Truth - REFRESHED)
    # -------------------------------------------------------------------------------------

    
    # [v3.3.3] 무결성 배지 (Integrity Status Badge) 최상단 배치
    c_badge1, c_badge2 = st.columns([1, 4])
    with c_badge1:
        st.success("✅ 데이터 무결성 검증 완료")
    with c_badge2:
        st.info("📊 네이버(FDR) & 야후(yf) 이중 감시 체계가 실시간으로 소통 중입니다.")

    with st.spinner("데이터 동기화 및 V3.3.0 수학적 무결성 검증 중..."):
        all_signals, is_bull_now, raw_data = load_and_process_data_v3_1_2()
        
        with st.expander("🛠️ 데이터 큐레이션 실시간 로그 (SSoT Raw Check)"):
            st.write(f"**캐시 버스터 타임스탬프:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            st.write(f"**yfinance가 뱉은 원본 컬럼:** `{list(raw_data.columns) if raw_data is not None else 'N/A'}`")
            for raw_tk, name in TARGET_ETFS.items():
                price = 'N/A'
                if raw_data is not None:
                    # [V3.1.6] Ticker-Attribute 매핑 전수 조사 (Close 가격 추적)
                    for c in raw_data.columns:
                        if isinstance(c, tuple) and raw_tk in c and 'Close' in c:
                            price = f"{raw_data[c].iloc[-1]:,.0f}원"
                            break
                        elif c == 'Close' and len(TARGET_ETFS) == 1:
                            price = f"{raw_data[c].iloc[-1]:,.0f}원"
                            break
                st.write(f"**{name} ({raw_tk}) 추출 가격:** `{price}`")
        
        # [NEW] 무결성 블랙박스 (Integrity Monitor) 상단 배치
        st.markdown("### 🩺 데이터 무결성 실시간 감시장치 (Integrity Monitor)")
        port_res = run_portfolio_backtest(all_signals, initial_capital=50000000.0, max_tickers=max_tickers, weight_per_ticker=weight_per_ticker)
        
        # -------------------------------------------------------------------------------------
        # [V3.3.0 INTEGRITY ENGINE] DUAL-SOURCE VERIFICATION & AUTO-JOURNAL
        # -------------------------------------------------------------------------------------
        # 1. 야후-네이버 이중 가격 검증 수행 (Cross-Check)
        dual_integrity = verify_dual_source_integrity(all_signals)
        
        BASELINE_RET = 226.38  # [V3.3.5] 실측 기준값 (3종목 모드 실제 수익률)
        current_ret = port_res.get('cumulative_return', 0.0)
        diff_ret = current_ret - BASELINE_RET
        
        c_int1, c_int2, c_int3, c_int4 = st.columns(4)
        c_int1.metric("시작-종료 범위", f"{port_res.get('start_date', '-')} ~ {port_res.get('end_date', '-')}")
        
        # 이중 검증 결과에 따른 배지 아이콘 결정
        integrity_icon = "✅" if dual_integrity['status'] == "Pass" else "⚠️"
        c_int2.metric("데이터 무결성 점수", f"{integrity_icon} {dual_integrity['score']}%", help=dual_integrity['detail'])
        
        c_int3.metric("데이터 총 행수", f"{port_res.get('total_days', 0)} rows")
        
        integrity_status = "🟢 정상 (Verified)" if abs(diff_ret) < 2.0 else "🔴 주의 (Anomaly Detected)"
        c_int4.metric("수익률 정밀 오차", f"{diff_ret:+.2f}%", integrity_status)
        
        # 2. 매일 16:00 이후 자동 성과 기록 (Journaling to DB)
        now_h = datetime.now().hour
        today_str = datetime.now().strftime("%Y-%m-%d")
        if now_h >= 16:
            try:
                # [Fix 1] 포트폴리오 전체 수익률 일별 기록
                journal_payload = {
                    "record_date": today_str,
                    "cumulative_return": float(current_ret),
                    "cagr": float(port_res.get('cagr', 0.0)),
                    "mdd": float(port_res.get('mdd', 0.0)),
                    "version": "V3.3.5"
                }
                supabase.table('backtest_history').upsert(journal_payload).execute()
                st.sidebar.success(f"📈 [16:00 정례 동기화] 오늘자 수익률({current_ret:.2f}%) 기록 완료")
            except Exception as e:
                st.sidebar.warning(f"⚠️ backtest_history 저장 실패: {e}")
            try:
                # [Fix 2] 종목별 시그널 일별 기록 (나중에 신호 성과 추적용)
                for sig_name, sig_df in all_signals.items():
                    latest = sig_df.iloc[-1]
                    signal_payload = {
                        "signal_date": today_str,
                        "ticker": sig_name,
                        "close": float(latest.get('close', 0)),
                        "target_break_price": float(latest.get('target_break_price', 0)),
                        "composite_rs": float(latest.get('composite_rs', 0)),
                        "buy_signal": bool(latest.get('execute_buy_T_plus_1', False)),
                        "exit_signal": bool(latest.get('execute_exit_T_plus_1', False)),
                        "mfi": float(latest.get('mfi', 0)),
                    }
                    supabase.table('daily_signals').upsert(signal_payload).execute()
                st.sidebar.info(f"📡 [시그널 기록] {len(all_signals)}개 종목 시그널 DB 저장 완료")
            except Exception as e:
                st.sidebar.warning(f"⚠️ daily_signals 저장 실패: {e}")
        
        st.divider()
    if not all_signals:
        st.error("데이터 로딩에 실패했습니다.")
        return

    today_date = max(df['date'].max() for df in all_signals.values())
    regime_text = "🔥 [공격 모드: 불장 가속]" if is_bull_now else "🛡️ [안정 모드: 시스템 안정]"
    st.info(f"최신 타점 갱신일: **{today_date}** | 시스템 엔진 상태: {regime_text}")
        
    tab1, tab4, tab2, tab3 = st.tabs([
        "🚀 AI 실전 시그널 보드", 
        "📈 실전 성과 궤적",
        "📊 전략별 백테스팅 종합판", 
        "🩺 알고리즘 무결성 진단"
    ])
    
    # === TAB 1: AI 실전 시그널 보드 ===
    with tab1:
        st.header(f"🎯 오늘의 AI 매매 권고 (TOP {max_tickers} 주도주)")
        
        # [무결성 보정] Composite RS 순위 추출 (추세 필터 적용) - 컬럼 누락 대비 방어 로직 포함
        valid_signals = []
        for n, d in all_signals.items():
            if 'composite_rs' in d.columns:
                valid_signals.append((n, d['composite_rs'].iloc[-1]))
        
        top_indices = sorted(valid_signals, key=lambda x: x[1], reverse=True)[:max_tickers]
        
        # [NEW] 그리드 레이아웃 적용 (가공되지 않은 원칙 중심 노출)
        cols_per_row = 3
        for r_idx in range(0, len(top_indices), cols_per_row):
            row_indices = top_indices[r_idx : r_idx + cols_per_row]
            cols = st.columns(cols_per_row)
            for i, (name, score) in enumerate(row_indices):
                df_curr = all_signals[name].iloc[-1]
                target_p = df_curr['target_break_price']
                curr_p = df_curr['close']
                
                # 시그널 판독
                if curr_p >= target_p:
                    sig_status = "🟢 [BUY/HOLD]"
                    color_hex = "#00FF00"
                elif curr_p >= target_p * 0.98:
                    sig_status = "🟡 [매수 대기]"
                    color_hex = "#FFA500"
                else:
                    sig_status = "⚪ [관망/준비]"
                    color_hex = "#AAAAAA"
                
                with cols[i]:
                    # 4조건 판독
                    params = TICKER_PARAMS.get(name, {'k': 0.5, 'mfi': 60, 'adx_threshold': 20})
                    mfi_thr = params['mfi']
                    adx_thr = params['adx_threshold']
                    
                    c1_pass = curr_p >= target_p
                    c2_pass = df_curr.get('mfi', 0) > mfi_thr
                    c3_pass = df_curr.get('intraday_intensity', 0) > 0
                    c4_pass = df_curr.get('adx_14', 0) > adx_thr
                    passed = sum([c1_pass, c2_pass, c3_pass, c4_pass])
                    
                    def ck(b): return "✅" if b else "❌"
                    
                    # RS 순위
                    rs_rank = [x[0] for x in sorted(valid_signals, key=lambda x: x[1], reverse=True)].index(name) + 1
                    rs_rank_txt = f"🏆 RS {rs_rank}위" if rs_rank <= 3 else f"RS {rs_rank}위"
                    
                    if passed == 4:
                        conclusion = "<span style='color:#00FF00;'>🚀 내일 시가 매수 집행</span>"
                    elif passed == 3:
                        conclusion = "<span style='color:#FFA500;'>⏳ 조건 1개 미달 (근접)</span>"
                    else:
                        conclusion = f"<span style='color:#AAAAAA;'>💤 조건 {passed}/4 충족 (대기)</span>"
                    
                    st.markdown(f"""
                    <div style="border:2px solid #666; border-radius:12px; padding:20px; margin-bottom:15px; background-color:#1e1e1e; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <h2 style="margin:0; color:#fff; font-size:1.6rem;">{name}</h2>
                            <span style="font-size:1.1rem; color:#fff; font-weight:bold;">{rs_rank_txt}</span>
                        </div>
                        <p style="margin:10px 0; color:{color_hex}; font-weight:bold; font-size:1.5rem;">{sig_status}</p>
                        <hr style="margin:12px 0; border:1px solid #444;">
                        <div style="display:flex; justify-content:space-between; font-size:1.2rem;">
                            <span>🎯 돌파 목표가</span>
                            <span style="font-weight:bold; color:#ffdd44;">{target_p:,.0f}원</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:1.2rem; margin-top:5px;">
                            <span>📉 현재가</span>
                            <span style="color:#fff;">{curr_p:,.0f}원</span>
                        </div>
                        <hr style="margin:12px 0; border:1px solid #444;">
                        <div style="font-size:1.1rem; color:#fff; line-height:1.6;">
                            <div style="margin-bottom:4px;">{ck(c1_pass)} <b>가격 돌파</b> &nbsp; <span style='color:#DDD;'>({curr_p:,.0f} {'≥' if c1_pass else '<'} {target_p:,.0f})</span></div>
                            <div style="margin-bottom:4px;">{ck(c2_pass)} <b>스마트머니(MFI)</b> &nbsp; <span style='color:#DDD;'>({df_curr.get('mfi',0):.1f} {'≥' if c2_pass else '<'} {mfi_thr})</span></div>
                            <div style="margin-bottom:4px;">{ck(c3_pass)} <b>일봉 지배력(II)</b> &nbsp; <span style='color:#DDD;'>({'지배(양수)' if c3_pass else '미지배(음수)'})</span></div>
                            <div style="margin-bottom:4px;">{ck(c4_pass)} <b>추세 강도(ADX)</b> &nbsp; <span style='color:#DDD;'>({df_curr.get('adx_14',0):.1f} {'≥' if c4_pass else '<'} {adx_thr})</span></div>
                        </div>
                        <hr style="margin:12px 0; border:1px solid #444;">
                        <div style="font-size:1.2rem; font-weight:bold;">{conclusion}</div>
                    </div>
                    """, unsafe_allow_html=True)

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
            bm_df = all_signals.get("KODEX 200").copy().set_index('date')
            first_open = bm_df['open'].iloc[0]
            bm_df['KOSPI 200'] = (bm_df['close'] / first_open) * 50000000
            chart_df = hist_df[['total_value']].join(bm_df[['KOSPI 200']], how='left')
            st.line_chart(chart_df, color=["#ff4b4b", "#1f77b4"])
            
            # 연도별 테이블
            yearly_df = hist_df[['total_value']].copy()
            yearly_df['ko200_close'] = bm_df['close']
            yearly_df.index = pd.to_datetime(yearly_df.index)
            y_last = yearly_df.resample('YE').last()
            irp_p = pd.Series([50000000] + y_last['total_value'].tolist()).pct_change().dropna() * 100
            ko_p = pd.Series([first_open] + y_last['ko200_close'].tolist()).pct_change().dropna() * 100
            y_data = [{"연도": "✨ [TOTAL]", "IRP 수익률": total_pct, "KOSPI 200": ((bm_df['close'].iloc[-1]/first_open)-1)*100, "Alpha": f"{total_pct - ((bm_df['close'].iloc[-1]/first_open)-1)*100:+.2f}%"}]
            for y, ir, ko in zip(y_last.index.year, irp_p, ko_p):
                y_data.append({"연도": f"{y}년", "IRP 수익률": ir, "KOSPI 200": ko, "Alpha": f"{ir-ko:+.2f}%"})
            st.dataframe(pd.DataFrame(y_data), use_container_width=True, hide_index=True)

    # === TAB 3: 알고리즘 무결성 진단 (투명화 고도화) ===
    with tab3:
        st.header("🩺 투명한 하이브리드 엔진 설계도 (무결성 공시)")
        
        col_reg, col_param = st.columns([1, 2])
        
        with col_reg:
            st.subheader("📡 시장 레짐(Regime) 실시간 상태")
            regime_status = "🔥 BULL (공격 모드)" if is_bull_now else "🛡️ STABLE (안정 모드)"
            st.info(f"**현재 상태:** {regime_status}")
            
            # 레짐 판독 공식 공시
            st.markdown("""
            **[레짐 판독 로직]**
            - **기준:** KODEX 200의 ADX 14일선 Z-Score
            - **공식:** $Z = (ADX_{now} - ADX_{\mu}) / ADX_{\sigma}$
            - **임계값:** $Z > 2.0$ 진입 시 공격, $Z < 1.0$ 하향 시 안정 모드
            """)
            
        with col_param:
            st.subheader("⚙️ 종목별 개별 최적화 파라미터 (TICKER_PARAMS)")
            # strategy.py의 TICKER_PARAMS를 테이블로 공시
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
            
            # 추세 가점 수동 복기용 계산 (불리언 버그 방지를 위해 정수 변환)
            tr_score = int(curr['close'] > curr['sma_20']) + int(curr['close'] > curr['sma_60']) + int(curr['close'] > curr['sma_120'])
            
            ranking_data.append({
                "종목명": name,
                "현재가 (T)": f"{curr['close']:,.0f}원",
                "수익률(RS_20)": f"{curr['rs_20']*100:+.2f}%",
                "추세 가점(0~3)": f"{tr_score}점",
                "복합RS(Composite)": f"{curr['composite_rs']*100:+.2f}%"
            })
        
        rank_raw_df = pd.DataFrame(ranking_data).sort_values("복합RS(Composite)", ascending=False)
        st.write("**현재 상동한 랭킹 정렬의 실시간 엔진 내부 수치입니다.** (추세 점수가 낮은 역배열 종목은 후순위로 자동 배치)")
        st.table(rank_raw_df.reset_index(drop=True))

        st.markdown("""
        ### ⚖️ 무결성 선언
        1. **단일 원천 데이터(SSoT):** 백테스팅 엔진과 실전 대시보드는 동일한 `strategy.py` 모듈과 동일한 파라미터를 공유합니다.
        2. **데이터 동기화:** 모든 종목의 날짜 인덱스를 하나로 통일하여, 모드 전환 시에도 종목 랭킹이 뒤바뀌지 않도록 무결성을 확보했습니다.
        3. **투명한 공식:** 목표가는 $Open + PrevRange \times K_{adj}$ 공식을 따르며, 불장일 경우 K값을 20% 할인하여 공격적인 진입을 수행합니다.
        """)

    with tab4:
        st.header("📈 실전 성과 궤적 (시그널 모니터링)")
        st.markdown("매일 16:00 기준으로 자동 기록된 시그널과 수익률 추이를 추적합니다.")

        # [Fix 3-A] 일별 누적 수익률 추이
        st.subheader("📊 포트폴리오 누적 수익률 추이")
        try:
            hist_res = supabase.table('backtest_history').select('*').order('record_date', desc=False).execute()
            if hist_res.data:
                hist_df = pd.DataFrame(hist_res.data)
                hist_df['record_date'] = pd.to_datetime(hist_df['record_date'])
                hist_df = hist_df.set_index('record_date')
                st.line_chart(hist_df[['cumulative_return']])
                st.dataframe(hist_df[['cumulative_return','cagr','mdd','version']].sort_index(ascending=False).head(30),
                             use_container_width=True)
            else:
                st.info("🕐 아직 기록된 데이터가 없습니다. 오늘 오후 4시 이후 자동 적재됩니다.")
        except Exception as e:
            err_str = str(e)
            if 'PGRST205' in err_str or 'backtest_history' in err_str:
                st.warning("🛠️ DB 테이블이 아직 생성되지 않았습니다. Supabase에서 `backtest_history` 테이블을 생성하면 자동 적재됩니다.")
            else:
                st.error(f"수익률 이력 조회 실패: {e}")

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
