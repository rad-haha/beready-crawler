# Beready - Crawler

학교 식단표를 자동으로 크롤링하고, 주간 식단을 정리하여 출력하는 Python 프로그램입니다.  
향후에는 Excel 저장, GitHub 업로드, 보고서 작성 기능을 추가할 예정입니다.

---

## 📌 주요 기능
- Selenium + ChromeDriver를 이용한 크롤링
- HTML 테이블 파싱 후 식단 데이터 추출
- 중복/불필요한 항목(운영사항, 구분 등) 제거
- 주간 단위 식단 출력

---

## ⚙️ 설치 방법
```bash
# 프로젝트 클론
git clone https://github.com/네아이디/cafeteria.git
cd cafeteria

# 가상환경 생성 및 활성화 (선택)
python -m venv venv
source venv/bin/activate  # (Windows: venv\Scripts\activate)

# 필요 라이브러리 설치
pip install -r requirements.txt
