"""
KRX KIND 신규상장기업현황 크롤링
- IPO현황 > 신규상장기업 > 신규상장기업현황
- 상장유형: 신규상장만 (이전상장/재상장 제외)
- 선택조건: 액면가, 공모가, 공모금액, 주요제품, 최초상장주식수
"""

import requests
from bs4 import BeautifulSoup
import re
import time


def parse_number(text):
    """숫자 텍스트를 정수/실수로 변환 (콤마, 공백 제거)"""
    if not text:
        return None
    cleaned = text.strip().replace(",", "").replace(" ", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        try:
            return float(cleaned)
        except ValueError:
            return None


def get_kind_ipo_list(start_date="2016-01-01", end_date="2026-12-31", market_type="kosdaqMkt"):
    """
    KIND 신규상장기업현황에서 신규상장 기업 목록 조회

    market_type: "kosdaqMkt"(코스닥) / "stockMkt"(유가증권)
    내부적으로 KIND API의 marketType 값으로 변환: 1(유가증권) / 2(코스닥)
    """
    url = "https://kind.krx.co.kr/listinvstg/listingcompany.do"

    # market_type 변환 (기존 호출부 호환)
    market_code = "2" if market_type == "kosdaqMkt" else "1"
    market_label = "코스닥" if market_type == "kosdaqMkt" else "유가증권"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain",
        "X-Requested-With": "XMLHttpRequest",
    }

    data = {
        "method": "searchListingTypeSub",
        "forward": "listingtype_sub",
        "currentPageSize": "3000",
        "pageIndex": "1",
        "orderMode": "1",
        "orderStat": "D",
        "marketType": market_code,
        "searchCorpName": "",
        "country": "",
        "industry": "",
        "repMajAgntDesignAdvserComp": "",
        "repMajAgntComp": "",
        "designAdvserComp": "",
        "listTypeArrStr": "01|",           # 신규상장만
        "choicTypeArrStr": "01|02|03|04|05|",  # 액면가/공모가/공모금액/주요제품/최초상장주식수
        "secuGrpArrStr": "0|ST|FS|MF|SC|RT|IF|DR|",  # 전체 증권구분
        "fromDate": start_date,
        "toDate": end_date,
    }

    resp = requests.post(url, data=data, headers=headers, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "lxml")

    results = []
    rows = soup.select("table tbody tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 12:
            continue

        company_name = cells[0].get_text(strip=True)
        if not company_name:
            continue

        # 시장구분 아이콘으로 판별 (icn_t_yu=유가, icn_t_ko=코스닥)
        img = cells[0].find("img")
        if img:
            src = img.get("src", "")
            if "icn_t_yu" in src:
                detected_market = "유가증권"
            elif "icn_t_ko" in src:
                detected_market = "코스닥"
            else:
                detected_market = market_label
        else:
            detected_market = market_label

        # onclick에서 종목코드 추출
        onclick = row.get("onclick", "")
        stock_code_match = re.search(r"'(\w+)'", onclick)
        stock_code = stock_code_match.group(1) if stock_code_match else None

        # SPAC 필터링
        spac_keywords = ["스팩", "SPAC", "기업인수목적"]
        combined = f"{company_name} {cells[4].get_text(strip=True)} {cells[10].get_text(strip=True)}"
        if any(kw in combined for kw in spac_keywords):
            continue

        # 리츠/인프라/예탁증권 필터링 (증권구분이 '주권'이 아닌 것 제외)
        sec_type = cells[3].get_text(strip=True)
        if sec_type and sec_type != "주권":
            continue

        info = {
            "회사명": company_name,
            "종목코드": stock_code,
            "상장일": cells[1].get_text(strip=True),
            "상장유형": cells[2].get_text(strip=True),
            "증권구분": cells[3].get_text(strip=True),
            "업종": cells[4].get_text(strip=True),
            "국적": cells[5].get_text(strip=True),
            "대표주관회사": cells[6].get_text(strip=True),
            "액면가": parse_number(cells[7].get_text(strip=True)),
            "확정공모가": parse_number(cells[8].get_text(strip=True)),
            "확정공모금액_억원": round(parse_number(cells[9].get_text(strip=True)) / 100000, 2) if parse_number(cells[9].get_text(strip=True)) else None,  # 천원 → 억원 (1억 = 100,000천원)
            "주요제품": cells[10].get_text(strip=True),
            "최초상장주식수": parse_number(cells[11].get_text(strip=True)),
            "시장구분": detected_market,
        }
        results.append(info)

    return results


def parse_price_number(text):
    """주가/등락률 텍스트 파싱. '0' 또는 '0.0'이면 None (기간 미경과)."""
    if not text:
        return None
    cleaned = text.strip().replace(",", "").replace(" ", "")
    if not cleaned or cleaned == "-":
        return None
    # 0 / 0.0 → 기간 미경과로 None 처리
    try:
        val = float(cleaned)
        if val == 0.0:
            return None
        # 정수로 표현 가능하면 정수 반환
        if val == int(val) and "." not in cleaned:
            return int(val)
        return val
    except ValueError:
        return None


def get_kind_price_performance(start_date, end_date):
    """
    KIND 공모가대비주가추이에서 상장일시가~1년 수익률 조회.
    최대 3년 범위 제한. SPAC 제외.

    Returns: list of dicts with keys:
        회사명, 주관사, 상장일, 공모가,
        상장일시가, 상장일시가등락률, 상장일종가, 상장일종가등락률,
        개월1_주가, 개월1_등락률, 개월3_주가, 개월3_등락률,
        개월6_주가, 개월6_등락률, 년1_주가, 년1_등락률
    """
    url = "https://kind.krx.co.kr/listinvstg/pubprcCmpStkprcByIssue.do"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://kind.krx.co.kr/listinvstg/pubprcCmpStkprcByIssue.do?method=pubprcCmpStkprcByIssueMain",
        "X-Requested-With": "XMLHttpRequest",
    }

    data = {
        "method": "pubprcCmpStkprcByIssueSub",
        "forward": "pubprcCmpStkprcByIssue_sub",
        "currentPageSize": "3000",
        "pageIndex": "1",
        "orderMode": "1",
        "orderStat": "D",
        "marketType": "",
        "fromDate": start_date,
        "toDate": end_date,
        "searchCorpName": "",
    }

    resp = requests.post(url, data=data, headers=headers, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "lxml")

    results = []
    rows = soup.select("table tbody tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 17:
            continue

        company_name = cells[0].get_text(strip=True)
        if not company_name:
            continue

        # SPAC 필터링
        spac_keywords = ["스팩", "SPAC", "기업인수목적"]
        if any(kw in company_name for kw in spac_keywords):
            continue

        info = {
            "회사명": company_name,
            "주관사": cells[1].get_text(strip=True),
            "상장일": cells[2].get_text(strip=True),
            "공모가": parse_number(cells[3].get_text(strip=True)),
            # col 4 = 수정공모가 (skip)
            "상장일시가": parse_price_number(cells[5].get_text(strip=True)),
            "상장일시가등락률": parse_price_number(cells[6].get_text(strip=True)),
            "상장일종가": parse_price_number(cells[7].get_text(strip=True)),
            "상장일종가등락률": parse_price_number(cells[8].get_text(strip=True)),
            "개월1_주가": parse_price_number(cells[9].get_text(strip=True)),
            "개월1_등락률": parse_price_number(cells[10].get_text(strip=True)),
            "개월3_주가": parse_price_number(cells[11].get_text(strip=True)),
            "개월3_등락률": parse_price_number(cells[12].get_text(strip=True)),
            "개월6_주가": parse_price_number(cells[13].get_text(strip=True)),
            "개월6_등락률": parse_price_number(cells[14].get_text(strip=True)),
            "년1_주가": parse_price_number(cells[15].get_text(strip=True)),
            "년1_등락률": parse_price_number(cells[16].get_text(strip=True)),
            # cols 17-18 = 최근거래일 (skip)
        }
        results.append(info)

    return results


def update_db_with_price_data(db_path=None):
    """
    KIND 공모가대비주가추이를 3년 윈도우로 스크래핑하여 DB에 업데이트.
    회사명으로 매칭하여 주가 수익률 컬럼만 갱신.
    """
    import sqlite3
    import os

    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipo_data.db")

    # 3년 윈도우 정의
    windows = [
        ("2016-01-01", "2018-12-31"),
        ("2019-01-01", "2021-12-31"),
        ("2022-01-01", "2024-12-31"),
        ("2025-01-01", "2026-12-31"),
    ]

    price_fields = [
        "상장일시가", "상장일시가등락률",
        "상장일종가", "상장일종가등락률",
        "개월1_주가", "개월1_등락률",
        "개월3_주가", "개월3_등락률",
        "개월6_주가", "개월6_등락률",
        "년1_주가", "년1_등락률",
    ]

    # 모든 윈도우에서 데이터 수집
    all_data = {}
    for start, end in windows:
        print(f"  스크래핑: {start} ~ {end} ...", end=" ", flush=True)
        records = get_kind_price_performance(start, end)
        print(f"{len(records)}건")
        for rec in records:
            # 회사명 기준으로 마지막 레코드 우선 (중복 시 덮어씀)
            all_data[rec["회사명"]] = rec
        time.sleep(1)

    print(f"  총 수집: {len(all_data)}건")

    # DB 업데이트
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 기존 회사명 목록 조회
    db_companies = conn.execute("SELECT id, 회사명 FROM ipo_companies").fetchall()
    db_name_map = {row["회사명"]: row["id"] for row in db_companies}

    update_sql = f"""
        UPDATE ipo_companies SET
            {', '.join(f'{f} = ?' for f in price_fields)},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """

    matched = 0
    for name, rec in all_data.items():
        if name in db_name_map:
            values = [rec.get(f) for f in price_fields]
            values.append(db_name_map[name])
            conn.execute(update_sql, values)
            matched += 1

    conn.commit()
    conn.close()

    unmatched = len(all_data) - matched
    print(f"  DB 매칭: {matched}건 업데이트, {unmatched}건 미매칭")
    return matched, unmatched


if __name__ == "__main__":
    print("=" * 70)
    print("KIND 신규상장기업현황 크롤링 테스트")
    print("=" * 70)

    for market, label in [("kosdaqMkt", "코스닥"), ("stockMkt", "유가증권")]:
        print(f"\n{'─' * 70}")
        print(f"  {label} 신규상장 (2016~현재)")
        print(f"{'─' * 70}")
        companies = get_kind_ipo_list(start_date="2016-01-01", market_type=market)
        print(f"  총 {len(companies)}건\n")
        for i, c in enumerate(companies[:10]):
            print(f"  [{i+1:3d}] {c['회사명']:<18s} {c['상장일']}  공모가={c['확정공모가']}  공모금액={c['확정공모금액_억원']}억  주관={c['대표주관회사']}")
        if len(companies) > 10:
            print(f"  ... 외 {len(companies)-10}건")

    # 전체 합계
    kosdaq = get_kind_ipo_list(start_date="2016-01-01", market_type="kosdaqMkt")
    kospi = get_kind_ipo_list(start_date="2016-01-01", market_type="stockMkt")
    print(f"\n{'=' * 70}")
    print(f"합계: 코스닥 {len(kosdaq)}건 + 유가증권 {len(kospi)}건 = {len(kosdaq) + len(kospi)}건")
    print(f"{'=' * 70}")
