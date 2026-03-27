import os
import sys
from dotenv import load_dotenv

# supabase package
try:
    from supabase import create_client, Client
except ImportError:
    print("Error: 'supabase' package is not installed. Run 'pip install -r requirements.txt'")
    sys.exit(1)

# 상위 폴더의 .env에서 환경 변수 가져오기
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
dotenv_path = os.path.join(root_dir, '.env')

load_dotenv(dotenv_path)

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("SUPABASE_URL 또는 SUPABASE_KEY가 .env 파일에 없습니다.")

supabase: Client = create_client(url, key)

def get_supabase_client() -> Client:
    return supabase
