import pandas as pd

def get_top_sectors_for_week(all_signals_dict: dict, target_date: str) -> list:
    """
    [실전용 스크리너]
    target_date 기준으로 RS 20일 상위 3개 종목과 그 점수를 추출하여 리턴합니다.
    형태: [('KODEX 200', 0.152), ('KODEX 반도체', 0.081), ...]
    """
    rs_scores = {}
    for ticker, df in all_signals_dict.items():
        # target_date 시점의 과거 데이터만 추출하여 룩어헤드 방지
        past_df = df[df['date'] <= target_date]
        if not past_df.empty:
            last_row = past_df.iloc[-1]
            if not pd.isna(last_row.get('rs_20')):
                rs_scores[ticker] = last_row['rs_20']
                
    # RS(상대강도) 기준 내림차순 정렬
    sorted_tickers = sorted(rs_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_tickers[:3]
