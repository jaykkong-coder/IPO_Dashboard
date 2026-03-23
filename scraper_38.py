"""
38커뮤니케이션에서 수요예측/청약 데이터 크롤링
- 기관경쟁률, 의무보유확약 비율, 청약경쟁률(비례)
"""

import requests
from bs4 import BeautifulSoup
import re
import time


def get_38_company_list(pages=10):
    """38커뮤니케이션 IPO 목록에서 회사명 → 상세 페이지 번호 매핑"""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    companies = {}
    for page in range(1, pages + 1):
        resp = session.get(
            "http://www.38.co.kr/html/fund/index.htm",
            params={"o": "k", "page": str(page)},
            timeout=10,
        )
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "lxml")

        for a in soup.find_all("a"):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if "o=v" in href and text and len(text) > 1:
                match = re.search(r"no=(\d+)", href)
                if match:
                    companies[text] = int(match.group(1))

        time.sleep(0.3)

    return companies


def get_38_detail(no):
    """38커뮤니케이션 상세 페이지에서 수요예측/청약 데이터 추출"""
    resp = requests.get(
        f"http://www.38.co.kr/html/fund/index.htm?o=v&no={no}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    resp.encoding = "euc-kr"
    soup = BeautifulSoup(resp.text, "lxml")

    data = {}

    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)

        for row in rows:
            joined = " ".join(row)

            # 기관경쟁률: "기관경쟁률 231.87:1"
            if "기관경쟁률" in joined:
                match = re.search(r"기관경쟁률\s*([\d,.]+)\s*:\s*1", joined)
                if match:
                    val = match.group(1).replace(",", "")
                    try:
                        data["기관경쟁률"] = float(val)
                    except ValueError:
                        pass

            # 의무보유확약: "의무보유확약 17.12%"
            if "의무보유확약" in joined:
                match = re.search(r"의무보유확약\s*([\d.]+)\s*%", joined)
                if match:
                    data["의무보유확약비율"] = float(match.group(1))

            # 청약경쟁률: "청약경쟁률 390:1 (비례 780:1)"
            if "청약경쟁률" in joined:
                # 비례 경쟁률 우선
                match_prop = re.search(r"비례\s*([\d,.]+)\s*:\s*1", joined)
                if match_prop:
                    val = match_prop.group(1).replace(",", "")
                    try:
                        data["청약경쟁률_비례"] = float(val)
                    except ValueError:
                        pass

                # 전체 경쟁률
                match_total = re.search(r"청약경쟁률\s*([\d,.]+)\s*:\s*1", joined)
                if match_total:
                    val = match_total.group(1).replace(",", "")
                    try:
                        data["청약경쟁률"] = float(val)
                    except ValueError:
                        pass

    return data


def update_db_with_38_data(db_path="ipo_data.db"):
    """DB의 모든 completed 회사에 대해 38커뮤니케이션 데이터 업데이트"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    companies_db = conn.execute(
        "SELECT 회사명 FROM ipo_companies WHERE 처리상태='completed'"
    ).fetchall()
    company_names = [r[0] for r in companies_db]

    print("38커뮤니케이션 회사 목록 수집 중...")
    company_map = get_38_company_list(pages=15)
    print(f"  총 {len(company_map)}개 회사 목록 수집")

    success = 0
    fail = 0

    for name in company_names:
        if name in company_map:
            no = company_map[name]
            data = get_38_detail(no)

            if data:
                sets = []
                params = []
                for field in ["기관경쟁률", "의무보유확약비율", "청약경쟁률_비례"]:
                    if field in data:
                        sets.append(f"{field} = ?")
                        params.append(data[field])

                if sets:
                    params.append(name)
                    conn.execute(
                        f"UPDATE ipo_companies SET {', '.join(sets)} WHERE 회사명 = ?",
                        params,
                    )
                    print(f"  {name}: 기관{data.get('기관경쟁률', '-')}:1, 확약{data.get('의무보유확약비율', '-')}%, 비례{data.get('청약경쟁률_비례', '-')}:1")
                    success += 1
                else:
                    print(f"  {name}: 데이터 없음")
                    fail += 1
            else:
                print(f"  {name}: 파싱 실패")
                fail += 1

            time.sleep(0.5)
        else:
            print(f"  {name}: 38comm 목록에 없음")
            fail += 1

    conn.commit()
    conn.close()
    print(f"\n완료: 성공 {success}, 실패 {fail}")


if __name__ == "__main__":
    update_db_with_38_data()
