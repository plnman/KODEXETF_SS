# 🚀 KODEX IRP v3.1 하이브리드 클라우드 배포 가이드

본 가이드는 현재 로컬에서 완성된 지능형 V3.1 시스템을 **Streamlit Community Cloud**에 배포하여 언제 어디서든 접속 가능한 환경을 구축하기 위한 필수 단계입니다.

---

## 🛠️ Step 1: GitHub 프라이빗 저장소 생성
1. [GitHub](https://github.com/)에 접속하여 새로운 저장소(New Repository)를 생성합니다.
2. **반드시 [Private]**으로 설정하십시오. (Supabase 관련 설정이 노출되는 것을 방지합니다.)
3. 현재 프로젝트 폴더의 파일들을 업로드합니다.
   - **주의:** `.env` 파일은 업로드하지 않아도 됩니다. (Step 3에서 직접 입력합니다.)

## 🌐 Step 2: Streamlit Cloud 연동
1. [Streamlit Cloud](https://share.streamlit.io/)에 접속하여 GitHub 계정으로 로그인합니다.
2. **"Create app"** 버튼을 클릭하고 방금 생성한 GitHub 저장소를 선택합니다.
3. Main file path에 `frontend/app.py`를 입력합니다.

## 🔐 Step 3: Secrets 설정 (매우 중요)
로컬의 `.env` 파일 대신 클라우드 서버에 직접 전역 변수를 주입해야 합니다.
1. 배포 설정 페이지 하단의 **[Advanced settings...]** -> **[Secrets]** 메뉴로 들어갑니다.
2. 아래 내용을 복사하여 붙여넣으십시오:

```toml
SUPABASE_URL = "https://sflndkhlzdpnczvstobt.supabase.co"
SUPABASE_KEY = "sb_publishable_rWx7phipJu-72VWNzlvZfw_2XyVus_V"
SUPABASE_DB_PASSWORD = "Antigravity2026!@KODEX"
```
3. [Save]를 누르고 배포를 시작합니다.

## 🏁 Step 4: 배포 완료 및 접속
- 약 2~3분의 빌드 시간이 지나면 **`https://[사용자명]-kodex-irp.streamlit.app`** 형식의 전용 URL이 발급됩니다.
- 이제 스마트폰에서도 북마크해두고 AI 시그널을 실시간으로 확인하실 수 있습니다! 🕋🚀

---

> [!TIP]
> 배포 중 오류가 발생하면 에디터의 **`requirements.txt`** 파일에 오타가 없는지, 혹은 `app.py`의 파일 경로 설정이 올바른지 다시 한번 체크해 드리겠습니다. 언제든 말씀해 주세요!
