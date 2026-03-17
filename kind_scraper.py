"""
KRX KIND에서 상장법인 정보 크롤링
- 업종, 주요제품, 상장일, 대표자, 지역 등
"""

import requests
from bs4 import BeautifulSoup
import re
import time


def search_company_info(company_name, market_type="kosdaqMkt"):
    """
    KIND에서 회사 정보 조회
    market_type: kosdaqMkt(코스닥), stockMkt(유가증권)
    """
    url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
    params = {
        "method": "searchCorpList",
        "searchType": "13",
        "marketType": market_type,
        "comAbbrv": company_name,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage",
    }

    resp = requests.get(url, params=params, headers=headers)
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "lxml")

    # 결과 테이블에서 데이터 추출
    results = []
    rows = soup.select("table tbody tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 7:
            info = {
                "회사명": cells[0].get_text(strip=True),
                "업종": cells[1].get_text(strip=True),
                "주요제품": cells[2].get_text(strip=True),
                "상장일": cells[3].get_text(strip=True),
                "결산월": cells[4].get_text(strip=True),
                "대표자": cells[5].get_text(strip=True),
                "지역": cells[6].get_text(strip=True),
            }

            # 홈페이지 링크
            link = cells[0].find("a")
            if link and link.get("href"):
                info["상세링크"] = link["href"]

            results.append(info)

    return results


def get_kind_ipo_list(start_date="2025-01-01", end_date="2026-12-31", market_type="kosdaqMkt"):
    """
    KIND에서 상장일 기준으로 신규상장 법인 목록 조회
    상장일 내림차순 정렬 후 날짜 범위로 필터링
    """
    url = "https://kind.krx.co.kr/corpgeneral/corpList.do"

    all_results = []
    page = 1

    while True:
        params = {
            "method": "searchCorpList",
            "searchType": "13",
            "marketType": market_type,
            "orderMode": "3",       # 상장일 기준 정렬
            "orderStat": "D",       # 내림차순
            "pageIndex": page,
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage",
        }

        resp = requests.get(url, params=params, headers=headers)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        rows = soup.select("table tbody tr")
        if not rows:
            break

        stop_paging = False
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 7:
                listing_date = cells[3].get_text(strip=True)

                # 날짜 범위 체크 (내림차순이므로 start_date 이전이면 중단)
                if listing_date < start_date:
                    stop_paging = True
                    break

                if listing_date > end_date:
                    continue

                # 지역 셀에서 홈페이지 링크 제거
                region_text = cells[6].get_text(strip=True)
                if "홈페이지" in region_text:
                    region_text = region_text.replace("홈페이지 보기", "").strip()

                info = {
                    "회사명": cells[0].get_text(strip=True),
                    "업종": cells[1].get_text(strip=True),
                    "주요제품": cells[2].get_text(strip=True),
                    "상장일": listing_date,
                    "결산월": cells[4].get_text(strip=True),
                    "대표자": cells[5].get_text(strip=True),
                    "지역": region_text,
                    "시장구분": "코스닥" if market_type == "kosdaqMkt" else "유가증권",
                }
                all_results.append(info)

        if stop_paging:
            break

        page += 1
        time.sleep(0.3)

    return all_results


if __name__ == "__main__":
    # 테스트: 리브스메드 조회
    print("=" * 60)
    print("리브스메드 정보 조회")
    print("=" * 60)
    results = search_company_info("리브스메드")
    for r in results:
        for k, v in r.items():
            print(f"  {k}: {v}")

    # 2025년~현재 코스닥 신규상장 목록
    print(f"\n{'=' * 60}")
    print("2025년~현재 코스닥 신규상장 법인 목록")
    print("=" * 60)
    kosdaq_list = get_kind_ipo_list(start_date="2025-01-01", market_type="kosdaqMkt")
    print(f"총 {len(kosdaq_list)}건")
    for i, c in enumerate(kosdaq_list):
        print(f"  [{i:3d}] {c['회사명']:20s} | {c['업종'][:20]:20s} | {c['주요제품'][:30]:30s} | {c['상장일']}")

    # 2025년~현재 유가증권 신규상장 목록
    print(f"\n{'=' * 60}")
    print("2025년~현재 유가증권 신규상장 법인 목록")
    print("=" * 60)
    kospi_list = get_kind_ipo_list(start_date="2025-01-01", market_type="stockMkt")
    print(f"총 {len(kospi_list)}건")
    for i, c in enumerate(kospi_list):
        print(f"  [{i:3d}] {c['회사명']:20s} | {c['업종'][:20]:20s} | {c['주요제품'][:30]:30s} | {c['상장일']}")

    print(f"\n총 합계: 코스닥 {len(kosdaq_list)}건 + 유가증권 {len(kospi_list)}건 = {len(kosdaq_list) + len(kospi_list)}건")
