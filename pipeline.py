"""
IPO Dashboard - 일괄 처리 파이프라인
KIND 목록 → DART 투자설명서 검색 → 파싱 → DB 저장
"""

import os
import sys
import time
import requests
import zipfile
import io
import json
from lxml import etree

from kind_scraper import get_kind_ipo_list
from ipo_extractor import extract_ipo_data
from database import init_db, upsert_company, get_pending_companies, get_stats

DART_API_KEY = "359212a47d6222104789f5d610aa3896471f8227"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")

# SPAC 필터링 키워드
SPAC_KEYWORDS = ["스팩", "SPAC", "기업인수목적"]


def load_corp_codes():
    """DART 고유번호 파일 로드 (이름 → corp_code 매핑)"""
    corp_code_file = os.path.join(BASE_DIR, "CORPCODE.xml")

    if not os.path.exists(corp_code_file):
        print("DART 고유번호 파일 다운로드 중...")
        url = "https://opendart.fss.or.kr/api/corpCode.xml"
        resp = requests.get(url, params={"crtfc_key": DART_API_KEY})
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(BASE_DIR)

    tree = etree.parse(corp_code_file)
    root = tree.getroot()

    mapping = {}
    for corp in root.findall(".//list"):
        name = corp.findtext("corp_name", "")
        code = corp.findtext("corp_code", "")
        stock = corp.findtext("stock_code", "")
        if name and code:
            mapping[name] = {"corp_code": code, "stock_code": stock}

    return mapping


def search_prospectus(corp_code):
    """DART에서 투자설명서 검색"""
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de": "20240101",
        "end_de": "20261231",
        "pblntf_ty": "C",
        "page_count": 100,
    }

    resp = requests.get(url, params=params)
    data = resp.json()

    if data.get("status") != "000":
        return None, f"API: {data.get('message', 'unknown')}"

    filings = data.get("list", [])

    # 투자설명서 우선 (기재정정 포함), 일괄신고 제외
    exclude = ["일괄신고", "채무증권"]
    prospectus = [
        f for f in filings
        if "투자설명서" in f.get("report_nm", "")
        and not any(kw in f.get("report_nm", "") for kw in exclude)
    ]

    if prospectus:
        return prospectus[0], None

    # 증권신고서로 대체
    securities = [
        f for f in filings
        if "증권신고서" in f.get("report_nm", "")
        and "지분증권" in f.get("report_nm", "")
    ]

    if securities:
        return securities[0], None

    return None, "투자설명서/증권신고서 없음"


def download_and_parse(rcept_no, company_name, max_retries=3):
    """공시서류 다운로드 → 파싱 (이미 다운로드된 문서 재활용)"""
    save_dir = os.path.join(DOCS_DIR, company_name)
    os.makedirs(save_dir, exist_ok=True)

    # 이미 다운로드된 파일이 있으면 재활용
    existing_files = [f for f in os.listdir(save_dir) if f.endswith((".xml", ".html", ".htm"))] if os.path.exists(save_dir) else []

    if not existing_files:
        # 다운로드 (재시도 포함)
        for attempt in range(max_retries):
            try:
                url = "https://opendart.fss.or.kr/api/document.xml"
                params = {"crtfc_key": DART_API_KEY, "rcept_no": rcept_no}
                resp = requests.get(url, params=params, timeout=30)

                if b"<?xml" in resp.content[:100] and b"err_code" in resp.content[:500]:
                    return None, f"다운로드 에러: {resp.content[:200].decode('utf-8', errors='replace')}"

                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    for name in zf.namelist():
                        filepath = os.path.join(save_dir, name)
                        with open(filepath, "wb") as f:
                            f.write(zf.read(name))
                break
            except (requests.ConnectionError, requests.Timeout, zipfile.BadZipFile) as e:
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    return None, f"다운로드 실패: {str(e)[:80]}"

    # XML/HTML 파일 찾아서 파싱
    for fname in os.listdir(save_dir):
        if fname.endswith((".xml", ".html", ".htm")):
            filepath = os.path.join(save_dir, fname)
            try:
                data = extract_ipo_data(filepath)
                return data, None
            except Exception as e:
                return None, f"파싱 에러: {str(e)[:100]}"

    return None, "파싱 가능한 파일 없음"


def is_spac(company):
    """SPAC 여부 판단"""
    name = company.get("회사명", "")
    product = company.get("주요제품", "")
    sector = company.get("업종", "")
    combined = f"{name} {product} {sector}"
    return any(kw in combined for kw in SPAC_KEYWORDS)


def run_pipeline(skip_spac=True):
    """전체 파이프라인 실행"""
    print("=" * 60)
    print("IPO Dashboard 파이프라인 시작")
    print("=" * 60)

    # 1. DB 초기화
    init_db()

    # 2. KIND에서 목록 가져오기
    print("\n[1/4] KIND 상장법인 목록 수집...")
    kosdaq = get_kind_ipo_list(start_date="2025-01-01", market_type="kosdaqMkt")
    kospi = get_kind_ipo_list(start_date="2025-01-01", market_type="stockMkt")
    all_companies = kosdaq + kospi
    print(f"  코스닥: {len(kosdaq)}건, 유가증권: {len(kospi)}건, 합계: {len(all_companies)}건")

    # 3. SPAC 필터링 & DB 등록
    spac_count = 0
    registered = 0
    for company in all_companies:
        if skip_spac and is_spac(company):
            spac_count += 1
            company["처리상태"] = "skipped"
            company["처리메모"] = "SPAC"
        else:
            company["처리상태"] = "pending"

        upsert_company(company)
        registered += 1

    print(f"  DB 등록: {registered}건 (SPAC 제외: {spac_count}건)")

    # 4. DART 고유번호 로드
    print("\n[2/4] DART 고유번호 매핑...")
    corp_codes = load_corp_codes()
    print(f"  총 {len(corp_codes)}개 법인 코드 로드")

    # 5. 미처리 회사 처리
    pending = get_pending_companies()
    print(f"\n[3/4] 투자설명서 처리 시작 ({len(pending)}건)")
    print("-" * 60)

    success = 0
    fail = 0

    for i, company in enumerate(pending):
        name = company["회사명"]
        print(f"\n  [{i+1}/{len(pending)}] {name} ({company.get('상장일', '')})")

        # DART 고유번호 찾기
        corp_info = corp_codes.get(name)
        if not corp_info:
            # 부분 매칭 시도
            matches = [(k, v) for k, v in corp_codes.items() if name in k or k in name]
            if matches:
                corp_info = matches[0][1]
                print(f"    부분 매칭: {matches[0][0]}")
            else:
                print(f"    ❌ DART 고유번호 없음")
                upsert_company({**company, "처리상태": "failed", "처리메모": "DART 고유번호 없음"})
                fail += 1
                continue

        company["dart_corp_code"] = corp_info["corp_code"]

        # 투자설명서 검색
        filing, error = search_prospectus(corp_info["corp_code"])
        if error:
            print(f"    ❌ {error}")
            upsert_company({**company, "처리상태": "failed", "처리메모": error})
            fail += 1
            time.sleep(0.5)
            continue

        company["dart_rcept_no"] = filing["rcept_no"]
        print(f"    📄 {filing['report_nm']} ({filing['rcept_dt']})")

        # 다운로드 & 파싱
        ipo_data, error = download_and_parse(filing["rcept_no"], name)
        if error:
            print(f"    ❌ {error}")
            upsert_company({**company, "처리상태": "failed", "처리메모": error})
            fail += 1
            time.sleep(0.5)
            continue

        # DB 저장 - KIND 데이터(시장구분, 상장유형 등)를 extractor가 덮어쓰지 않도록 처리
        # extractor의 시장구분/상장유형 제거 (KIND 데이터가 정확함)
        ipo_data.pop("시장구분", None)
        ipo_data.pop("상장유형", None)
        merged = {**company, **ipo_data}
        merged["처리상태"] = "completed"
        merged["처리메모"] = filing["report_nm"]
        upsert_company(merged)

        extracted_count = sum(1 for k, v in ipo_data.items() if v is not None and v != 0)
        print(f"    ✅ {extracted_count}개 필드 추출")
        success += 1

        # API 속도 제한 (분당 1000건)
        time.sleep(1)

    # 6. 결과 요약
    stats = get_stats()
    print(f"\n{'=' * 60}")
    print("[4/4] 처리 완료")
    print(f"{'=' * 60}")
    print(f"  전체: {stats['total']}건")
    print(f"  성공: {stats['completed']}건")
    print(f"  실패: {stats['failed']}건")
    print(f"  SPAC 제외: {stats['skipped']}건")
    print(f"  미처리: {stats['pending']}건")


if __name__ == "__main__":
    run_pipeline()
