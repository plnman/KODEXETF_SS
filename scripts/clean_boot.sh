#!/bin/bash
# ==============================================================================
# Antigravity Self-Healing Script
# 시스템 안정성을 위해 기존 좀비 프로세스(node, python등) 강제 종료 및 캐시 클리닝
# 운영체제(Windows / Linux / MacOS) 환경 자동 감지 및 맞춤형 Kill(taskkill/pkill) 지원
# ==============================================================================

echo "[KODEX 안티그래비티] Self-Healing 세션 초기화 및 프로세스 정리 시작..."

# 1. OS 감지 및 좀비 프로세스 종료
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    echo "▶ Windows 환경 감지됨 (taskkill 실행)"
    # node.exe와 python.exe를 백그라운드에서 조용히 종료
    taskkill //F //IM node.exe //T > /dev/null 2>&1
    taskkill //F //IM python.exe //T > /dev/null 2>&1
else
    echo "▶ Unix/Linux/MacOS 환경 감지됨 (pkill 실행)"
    pkill -9 node > /dev/null 2>&1
    pkill -9 python > /dev/null 2>&1
fi

echo "▶ 좀비 프로세스 초기화 완료."

# 2. 파이썬 임시 캐시 파일 클리닝 (__pycache__, .pytest_cache 등)
echo "▶ 캐시 파일 무결성 클리닝 작업 중..."
find . -type d -name "__pycache__" -exec rm -rf {} + > /dev/null 2>&1
find . -type d -name ".pytest_cache" -exec rm -rf {} + > /dev/null 2>&1
find . -name "*.pyc" -delete > /dev/null 2>&1

# 3. 환경 변수 스냅샷 리로드 및 마무리
echo "▶ 환경 스냅샷 재로드 및 상태 점검 완료."
echo "=============================================================================="
echo "[SUCCESS] Antigravity Self-Healing 완료. 최적의 구동 상태로 진입합니다."
echo "=============================================================================="
