# -*- coding: utf-8 -*-
"""
PKNU 라일락 주간식단표 크롤러 (requests + BeautifulSoup, 최종)
- 목록(https://www.pknu.ac.kr/main/399)에서 최신 글 자동 진입
- 상세 페이지 첫 라일락 주간 표에서 '중식' 5일치 파싱
- SQLite: cafeteria.db / lilac_menu(day_text, menu)
"""

import re
import sqlite3
from typing import List, Tuple, Optional, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

LIST_URL = "https://www.pknu.ac.kr/main/399"
DB_PATH  = "cafeteria.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": LIST_URL,
    "Accept-Language": "ko,en;q=0.9",
    "Cache-Control": "no-cache",
}

# ---------------- HTTP ----------------
def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text

# ------------- 목록 → 최신 글 URL -------------
def find_latest_view_url(list_html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(list_html, "html.parser")

    # 1) 가장 보편적인 패턴: 본문 테이블의 제목칸 링크
    a = soup.select_one("td.title a[href*='action=view']")
    if a and a.get("href"):
        return urljoin(base_url, a["href"])

    # 2) 테이블 내부 아무 view 링크
    a = soup.select_one("table a[href*='action=view']")
    if a and a.get("href"):
        return urljoin(base_url, a["href"])

    # 3) 페이지 전체에서라도 view 링크
    a = soup.select_one("a[href*='action=view']")
    if a and a.get("href"):
        return urljoin(base_url, a["href"])

    return None

# ------------- 상세: 라일락 표 찾기 -------------
WEEK_EN  = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
DATE_PAT = re.compile(r"\d{1,2}\s*월\s*\d{1,2}\s*일")

def find_lilac_table(view_html: str) -> Optional[Tag]:
    soup = BeautifulSoup(view_html, "html.parser")

    # 우선순위 1: con03_sub_2 클래스
    t = soup.select_one("table.con03_sub_2")
    if t:
        return t

    # 우선순위 2~3: 요일/날짜가 보이는 테이블
    for table in soup.find_all("table"):
        first_tr = table.find("tr")
        if not first_tr:
            continue
        first_text = first_tr.get_text(" ", strip=True)
        if any(w in first_text for w in WEEK_EN) or DATE_PAT.search(first_text):
            return table

    # 최후: 첫 번째 table
    return soup.find("table")

# ------------- 유틸 -------------
def cell_text(el: Optional[Tag]) -> str:
    """셀 내부를 줄바꿈 기준으로 평탄화. (p/br/span 모두 대응)"""
    if not el:
        return ""
    return el.get_text("\n", strip=True).replace("\r", "")

def squash_slash(lines: List[str]) -> List[str]:
    """
    표 안에서 '/' 가 독립 span으로 끊겨 들어오는 경우
    ex) ['잡곡밥', '/', '현미밥'] -> ['잡곡밥/현미밥']
    """
    out: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        cur = lines[i]
        if cur == "/" and out and i + 1 < n:
            out[-1] = f"{out[-1]}/{lines[i+1]}"
            i += 2
            continue
        out.append(cur)
        i += 1
    return out

def pick_5_header(cells: List[Tag]) -> List[Tag]:
    """헤더용: '구분' / 빈칸 / '운영정보' 제외하고 Monday~Friday 5칸만"""
    picked = []
    for c in cells:
        tx = cell_text(c)
        if not tx or "구분" in tx or "운영정보" in tx:
            continue
        picked.append(c)
        if len(picked) == 5:
            break
    return picked

def pick_5_dates(cells: List[Tag]) -> List[Tag]:
    """날짜용: '운영정보' 제외하고 앞에서 5칸"""
    cleaned = [c for c in cells if "운영정보" not in cell_text(c)]
    return cleaned[:5]

# ------------- 표 파싱 (중식 5일) -------------
def parse_lunch_from_table(table: Tag) -> List[Tuple[str, str]]:
    rows_out: List[Tuple[str, str]] = []
    trs = table.find_all("tr")
    if len(trs) < 3:
        return rows_out

    # 헤더 2줄: 요일/날짜
    h1 = trs[0].find_all(["th", "td"])
    h2 = trs[1].find_all(["th", "td"])

    day_cells  = pick_5_header(h1)
    date_cells = pick_5_dates(h2)

    labels: List[str] = []
    for i in range(5):
        d_txt = cell_text(date_cells[i]) if i < len(date_cells) else ""
        w_txt = cell_text(day_cells[i])  if i < len(day_cells)  else ""
        if d_txt and w_txt and w_txt not in d_txt:
            labels.append(f"{d_txt} ({w_txt})")
        elif d_txt:
            labels.append(d_txt)
        elif w_txt:
            labels.append(w_txt)
        else:
            labels.append(f"Day{i+1}")

    # '중식' 행 찾기
    lunch_tr = None
    for tr in trs[2:]:
        first_two = tr.find_all(["th", "td"])[:2]
        left_text = " ".join(cell_text(c) for c in first_two)
        if "중식" in left_text:
            lunch_tr = tr
            break
    if not lunch_tr:
        lunch_tr = trs[2]  # fallback

    # 중식 행에서 월~금 5칸 추출
    tds = lunch_tr.find_all(["th", "td"])
    # 왼쪽 '구분' 칸(1~2칸) 위치 파악
    skip = 0
    for i, c in enumerate(tds[:2]):
        if "구분" in cell_text(c) or "중식" in cell_text(c):
            skip = i + 1
    if skip == 0:
        skip = 1
    candidates = [c for c in tds[skip:] if "운영정보" not in cell_text(c)]
    menu_cells = candidates[:5]

    # 각 칸 -> 줄 단위 메뉴, 운영문구 제거, 슬래시 병합
    ban_words = ("운영", "문의", "전화", "Open", "Close")
    for i, cell in enumerate(menu_cells):
        day = labels[i] if i < len(labels) else f"Day{i+1}"
        raw = cell_text(cell)
        lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
        lines = [ln for ln in lines if not any(b in ln for b in ban_words)]
        lines = squash_slash(lines)
        for dish in lines:
            rows_out.append((day, dish))

    return rows_out

# ------------- DB -------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lilac_menu(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day_text TEXT NOT NULL,
  menu TEXT NOT NULL,
  UNIQUE(day_text, menu)
);
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()

def upsert(items: List[Tuple[str, str]]) -> int:
    if not items:
        return 0
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    added = 0
    for day, menu in items:
        cur.execute("INSERT OR IGNORE INTO lilac_menu(day_text, menu) VALUES (?, ?)", (day, menu))
        if cur.rowcount:
            added += 1
    conn.commit()
    conn.close()
    return added

# ------------- 실행 -------------
def main():
    # 1) 목록 → 최신 글
    list_html = fetch_html(LIST_URL)
    view_url = find_latest_view_url(list_html, LIST_URL)
    if not view_url:
        print("[ERROR] 최신 글 링크를 못 찾았어.")
        return

    # 2) 상세 HTML
    view_html = fetch_html(view_url)

    # 3) 라일락 표 → 중식 파싱
    table = find_lilac_table(view_html)
    if not table:
        print("[ERROR] 라일락 표를 못 찾았어.")
        return
    items = parse_lunch_from_table(table)

    # 4) DB 저장 + 출력
    init_db()
    added = upsert(items)
    print(f"[DONE] TOTAL added: {added}\n")

    # 보기 좋게 그룹 출력
    grouped: Dict[str, List[str]] = {}
    for d, m in items:
        grouped.setdefault(d, []).append(m)
    for d in grouped:
        print(f"{d}:")
        print(" - " + " · ".join(grouped[d]))
        print()

if __name__ == "__main__":
    main()