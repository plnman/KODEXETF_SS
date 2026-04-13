"""
ETF Universe Single Source of Truth — V3.8.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
이 파일만 수정하면 전체 시스템 종목 구성이 자동으로 반영됩니다.
daily_scraper.py / strategy.py / app.py 는 수정 불필요.

종목 추가 방법:
  1. ETF_UNIVERSE 에 항목 1줄 추가
  2. 저장 — 끝.

raw_code 규칙:
  - 일반 종목: "069500.KS"  (6자리 숫자 + .KS)
  - 특수 코드: "0080G0"     (.KS 없이, 영숫자 혼합)
"""

# ─────────────────────────────────────────────────────────────────────────────
# MASTER ETF UNIVERSE  [V3.8.0]
# ─────────────────────────────────────────────────────────────────────────────
ETF_UNIVERSE = {
    # ── 국내 코어 ─────────────────────────────────────────────────────────────
    "069500.KS":  {"name": "KODEX 200",                   "k": 0.7, "mfi": 40, "adx_threshold": 15},
    "091160.KS":  {"name": "KODEX 반도체",                 "k": 0.2, "mfi": 50, "adx_threshold": 15},
    "091180.KS":  {"name": "KODEX 자동차",                 "k": 0.2, "mfi": 50, "adx_threshold": 15},
    "244580.KS":  {"name": "KODEX 바이오",                 "k": 0.2, "mfi": 60, "adx_threshold": 15},

    # ── 글로벌 지수 ────────────────────────────────────────────────────────────
    "379800.KS":  {"name": "KODEX 미국S&P500",             "k": 0.7, "mfi": 40, "adx_threshold": 15},
    "379810.KS":  {"name": "KODEX 미국나스닥100",           "k": 0.5, "mfi": 50, "adx_threshold": 15},
    "453810.KS":  {"name": "KODEX 인도Nifty50",            "k": 0.6, "mfi": 50, "adx_threshold": 15},

    # ── AI / 테크 메가트렌드 ───────────────────────────────────────────────────
    "485540.KS":  {"name": "KODEX 미국AI테크TOP10",        "k": 0.3, "mfi": 55, "adx_threshold": 20},
    "487230.KS":  {"name": "KODEX 미국AI전력핵심인프라",    "k": 0.3, "mfi": 55, "adx_threshold": 20},
    "487240.KS":  {"name": "KODEX AI전력핵심설비",          "k": 0.3, "mfi": 55, "adx_threshold": 20},
    "0151S0":     {"name": "KODEX 미국AI반도체TOP3플러스",  "k": 0.3, "mfi": 55, "adx_threshold": 20},
    "0173Y0":     {"name": "KODEX 미국AI광통신네트워크",    "k": 0.3, "mfi": 55, "adx_threshold": 20},

    # ── 방산 / 우주 / 로봇 ────────────────────────────────────────────────────
    "0167Z0":     {"name": "KODEX 미국우주항공",            "k": 0.4, "mfi": 55, "adx_threshold": 20},
    "0038A0":     {"name": "KODEX 미국휴머노이드로봇",      "k": 0.3, "mfi": 55, "adx_threshold": 20},
    "0080G0":     {"name": "KODEX 방산TOP10",              "k": 0.3, "mfi": 60, "adx_threshold": 20},
}

# ─────────────────────────────────────────────────────────────────────────────
# 파생 딕셔너리 (자동 생성 — 직접 수정 금지)
# ─────────────────────────────────────────────────────────────────────────────

# daily_scraper.TARGET_ETFS 형식: {raw_code: name}
TARGET_ETFS = {code: info["name"] for code, info in ETF_UNIVERSE.items()}

# app.py load_live_signals_only() 형식: {clean_code: name}  (.KS 제거)
ETFS_CLEAN = {code.replace(".KS", ""): info["name"] for code, info in ETF_UNIVERSE.items()}

# engine/strategy.TICKER_PARAMS 형식: {name: {k, mfi, adx_threshold}}
TICKER_PARAMS = {
    info["name"]: {"k": info["k"], "mfi": info["mfi"], "adx_threshold": info["adx_threshold"]}
    for info in ETF_UNIVERSE.values()
}

# verify_tickers() FDR 리스팅 대조 제외 코드 (숫자+영문자 혼합 FDR 전용 코드)
SKIP_LISTING_CHECK = {
    code.replace(".KS", "")
    for code in ETF_UNIVERSE
    if not code.replace(".KS", "").isdigit()
}
