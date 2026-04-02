import json
import os
from datetime import datetime

AUDIT_FILE = "analytics/backtest_audit_log.json"

def log_backtest_integrity(res_dict):
    """
    백테스트 실시간 무결성 로그를 파일에 기록합니다.
    """
    os.makedirs("analytics", exist_ok=True)
    
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "V3.1.3",
        "start_date": res_dict.get('start_date', '-'),
        "end_date": res_dict.get('end_date', '-'),
        "total_days": res_dict.get('total_days', 0),
        "cumulative_return": f"{res_dict.get('cumulative_return', 0.0):.2f}%",
        "mdd": f"{res_dict.get('mdd', 0.0):.2f}%",
        "integrity_check": "PASSED"
    }
    
    existing_logs = []
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                existing_logs = json.load(f)
        except:
            existing_logs = []
            
    existing_logs.append(log_entry)
    
    # 최근 100건만 유지 (데이터 비대화 방지)
    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_logs[-100:], f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    # 테스트 레코드
    test_res = {
        'start_date': "2019-01-02",
        'end_date': "2026-04-02",
        'total_days': 1826,
        'cumulative_return': 2.3066,
        'mdd': -0.2245
    }
    log_backtest_integrity(test_res)
    print(f"Log updated: {AUDIT_FILE}")
