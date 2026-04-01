import os
import sys
import psycopg2
import urllib.parse
from dotenv import load_dotenv

def deploy():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    dotenv_path = os.path.join(root_dir, '.env')
    
    load_dotenv(dotenv_path)
    url = os.environ.get("SUPABASE_URL")
    pwd = os.environ.get("SUPABASE_DB_PASSWORD")
    
    if not url or not pwd:
        print("Missing SUPABASE_URL or SUPABASE_DB_PASSWORD in .env")
        return
        
    # 특수문자(@ 등)가 포함된 비밀번호를 URL 파싱 오류 없이 연결하기 위해 인코딩
    pwd_encoded = urllib.parse.quote_plus(pwd)
    ref = url.replace("https://", "").split(".")[0]
    conn_str = f"postgresql://postgres:{pwd_encoded}@db.{ref}.supabase.co:5432/postgres"
    
    sql_path = os.path.join(root_dir, 'schema', 'create_live_trades_table.sql')
    if not os.path.exists(sql_path):
        print(f"SQL file not found at {sql_path}")
        return
        
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_query = f.read()
        
    try:
        print("Connecting to Supabase PostgreSQL...")
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql_query)
        print("✅ [SUCCESS] Successfully created 'live_trades' table in Supabase!")
        conn.close()
    except Exception as e:
        print(f"❌ [ERROR] Executing SQL Failed: {e}")
        
if __name__ == "__main__":
    deploy()
