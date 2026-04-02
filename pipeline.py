"""
IPO Dashboard - 일괄 처리 파이프라인
KIND 신규상장기업현황 → DART 투자설명서 검색 → 파싱 → DB 저장
"""

import os
import sys
import time
import requests
import zipfile
import io
from lxml import etree

from kind_scraper import get_kind_ipo_list
from ipo_extractor import extract_ipo_data
from database import init_db, upsert_company, get_pending_companies, get_stats

DART_API_KEY = "359212a47d6222104789f5d610aa3896471f8227"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")


def load_corp_codes():
    """DART 고유번호 파일 로드 (이름 → corp_code 매핑 + stock_code → corp_code 매핑)"""
    corp_code_file = os.path.join(BASE_DIR, "CORPCODE.xml")

    if not os.path.exists(corp_code_file):
        print("DART 고유번호 파일 다운로드 중...")
        url = "https://opendart.fss.or.kr/api/corpCode.xml"
        resp = requests.get(url, params={"crtfc_key": DART_API_KEY})
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(BASE_DIR)

    tree = etree.parse(corp_code_file)
    root = tree.getroot()

    name_map = {}
    stock_map = {}
    for corp in root.findall(".//list"):
        name = corp.findtext("corp_name", "")
        code = corp.findtext("corp_code", "")
        stock = corp.findtext("stock_code", "").strip()
        if name and code:
            name_map[name] = {"corp_code": code, "stock_code": stock}
        if stock and code:
            stock_map[stock] = {"corp_code": code, "corp_name": name}

    return name_map, stock_map


def search_prospectus(corp_code):
    """DART에서 투자설명서 검색 — 다운로드 가능한 것만 반환"""
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de": "20150101",
        "end_de": "20261231",
        "pblntf_ty": "C",
        "page_count": 100,
    }

    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            break
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt < 2:
                time.sleep(5)
            else:
                return None, f"연결 에러: {str(e)[:50]}"

    if data.get("status") != "000":
        return None, f"API: {data.get('message', 'unknown')}"

    filings = data.get("list", [])

    # 투자설명서 우선 (기재정정 포함), 일괄신고/채무증권 제외
    exclude = ["일괄신고", "채무증권"]
    prospectus = [
        f for f in filings
        if "투자설명서" in f.get("report_nm", "")
        and not any(kw in f.get("report_nm", "") for kw in exclude)
    ]

    if prospectus:
        prospectus.sort(key=lambda x: x.get("rcept_dt", ""))
        oldest_date = prospectus[0].get("rcept_dt", "")[:6]
        same_period = [p for p in prospectus if p.get("rcept_dt", "")[:6] <= oldest_date[:4] + "12"]
        if same_period:
            # 같은 시기 중 가장 최신 (정정본) 우선, 다운로드 불가 시 다음 후보
            same_period.sort(key=lambda x: x.get("rcept_dt", ""), reverse=True)
            return same_period, None
        return [prospectus[0]], None

    # 증권신고서로 대체 (지분증권만)
    securities = [
        f for f in filings
        if "증권신고서" in f.get("report_nm", "")
        and "지분증권" in f.get("report_nm", "")
    ]

    if securities:
        return [securities[0]], None

    return None, "투자설명서/증권신고서 없음"


def download_and_parse(filing_candidates, company_name, max_retries=2):
    """공시서류 다운로드 → 파싱 (다운로드 실패 시 다음 후보로 fallback)"""
    save_dir = os.path.join(DOCS_DIR, company_name)
    os.makedirs(save_dir, exist_ok=True)

    # 이미 다운로드된 파일이 있으면 재활용
    existing_files = [f for f in os.listdir(save_dir) if f.endswith((".xml", ".html", ".htm"))] if os.path.exists(save_dir) else []

    if existing_files:
        filepath = os.path.join(save_dir, existing_files[0])
        try:
            data = extract_ipo_data(filepath)
            return data, filing_candidates[0]["rcept_no"], None
        except Exception as e:
            return None, None, f"파싱 에러: {str(e)[:100]}"

    # 후보 순서대로 다운로드 시도
    for filing in filing_candidates:
        rcept_no = filing["rcept_no"]

        for attempt in range(max_retries):
            try:
                url = "https://opendart.fss.or.kr/api/document.xml"
                params = {"crtfc_key": DART_API_KEY, "rcept_no": rcept_no}
                resp = requests.get(url, params=params, timeout=30)

                # DART 에러 응답 (XML) — 다음 후보로
                if resp.content[:4] != b"PK\x03\x04":
                    break

                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    for name in zf.namelist():
                        safe_name = name.lstrip("/")
                        filepath = os.path.join(save_dir, safe_name)
                        with open(filepath, "wb") as f:
                            f.write(zf.read(name))

                # 파싱
                for fname in os.listdir(save_dir):
                    if fname.endswith((".xml", ".html", ".htm")):
                        filepath = os.path.join(save_dir, fname)
                        try:
                            data = extract_ipo_data(filepath)
                            return data, rcept_no, None
                        except Exception as e:
                            return None, rcept_no, f"파싱 에러: {str(e)[:100]}"

                return None, rcept_no, "파싱 가능한 파일 없음"

            except (requests.ConnectionError, requests.Timeout, zipfile.BadZipFile) as e:
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    break  # 다음 후보로

        # 이 후보 실패 — 다음 후보 시도 전 정리
        for f in os.listdir(save_dir):
            os.remove(os.path.join(save_dir, f))
        time.sleep(0.5)

    return None, None, "모든 후보 다운로드 실패"


def run_pipeline():
    """전체 파이프라인 실행"""
    print("=" * 60)
    print("IPO Dashboard 파이프라인 시작")
    print("=" * 60)

    # 1. DB 초기화
    init_db()

    # 2. KIND 신규상장기업현황에서 목록 수집 (SPAC/리츠 이미 제외됨)
    print("\n[1/4] KIND 신규상장기업현황 수집...")
    all_companies = get_kind_ipo_list(start_date="2016-01-01")
    kosdaq = [c for c in all_companies if c.get("시장구분") == "코스닥"]
    kospi = [c for c in all_companies if c.get("시장구분") == "유가증권"]
    print(f"  코스닥: {len(kosdaq)}건, 유가증권: {len(kospi)}건, 합계: {len(all_companies)}건")

    # 3. DB 등록 (신규만 pending, 기존 completed는 보호)
    import sqlite3
    db_path = os.path.join(BASE_DIR, "ipo_data.db")
    conn = sqlite3.connect(db_path)
    existing = set()
    for row in conn.execute("SELECT 회사명, 상장일 FROM ipo_companies WHERE 처리상태='completed'").fetchall():
        existing.add((row[0], row[1]))
    conn.close()

    new_count = 0
    for company in all_companies:
        key = (company.get("회사명"), company.get("상장일"))
        if key in existing:
            continue  # 이미 completed → 건드리지 않음
        company["처리상태"] = "pending"
        upsert_company(company)
        new_count += 1
    print(f"  DB 등록: {new_count}건 신규 (기존 completed {len(existing)}건 보호)")

    # 4. DART 고유번호 로드 (이름 매핑 + 종목코드 매핑)
    print("\n[2/4] DART 고유번호 매핑...")
    name_map, stock_map = load_corp_codes()
    print(f"  이름 매핑: {len(name_map)}개, 종목코드 매핑: {len(stock_map)}개")

    # 5. 미처리 회사 처리
    pending = get_pending_companies()
    print(f"\n[3/4] 투자설명서 처리 시작 ({len(pending)}건)")
    print("-" * 60)

    success = 0
    fail = 0

    for i, company in enumerate(pending):
        name = company["회사명"]
        print(f"\n  [{i+1}/{len(pending)}] {name} ({company.get('상장일', '')})")

        # DART 고유번호 찾기: ① 이름 매칭 → ② 종목코드 매칭 → ③ 부분 매칭
        corp_code = None

        # ① 정확한 이름 매칭
        corp_info = name_map.get(name)
        if corp_info:
            corp_code = corp_info["corp_code"]

        # ② KIND 종목코드 → DART stock_code (KIND코드 × 10)
        if not corp_code and company.get("종목코드"):
            dart_stock = (str(company["종목코드"]) + "0").zfill(6)
            stock_info = stock_map.get(dart_stock)
            if stock_info:
                corp_code = stock_info["corp_code"]
                print(f"    종목코드 매칭: {stock_info['corp_name']}")

        # ③ 부분 매칭
        if not corp_code:
            matches = [(k, v) for k, v in name_map.items() if name in k or k in name]
            if matches:
                corp_code = matches[0][1]["corp_code"]
                print(f"    부분 매칭: {matches[0][0]}")

        if not corp_code:
            print(f"    DART 고유번호 없음")
            upsert_company({**company, "처리상태": "failed", "처리메모": "DART 고유번호 없음"})
            fail += 1
            continue

        company["dart_corp_code"] = corp_code

        # 투자설명서 검색
        filing_candidates, error = search_prospectus(corp_code)
        if error:
            print(f"    {error}")
            upsert_company({**company, "처리상태": "failed", "처리메모": error})
            fail += 1
            time.sleep(0.5)
            continue

        print(f"    {filing_candidates[0]['report_nm']} ({filing_candidates[0]['rcept_dt']})")

        # 다운로드 & 파싱 (실패 시 다음 후보로 fallback)
        ipo_data, used_rcept_no, error = download_and_parse(filing_candidates, name)
        if error:
            print(f"    {error}")
            upsert_company({**company, "처리상태": "failed", "처리메모": error})
            fail += 1
            time.sleep(0.5)
            continue

        company["dart_rcept_no"] = used_rcept_no

        # DB 저장 — KIND 데이터가 정확하므로 extractor가 덮어쓰지 않도록 제거
        for kind_field in ["시장구분", "상장유형", "확정공모가", "확정공모금액_억원", "대표주관회사"]:
            ipo_data.pop(kind_field, None)

        merged = {**company, **ipo_data}
        merged["처리상태"] = "completed"
        merged["처리메모"] = filing_candidates[0]["report_nm"]
        upsert_company(merged)

        extracted_count = sum(1 for k, v in ipo_data.items() if v is not None and v != 0)
        print(f"    {extracted_count}개 필드 추출")
        success += 1

        # API 속도 제한 (안전 마진)
        time.sleep(1.5)

    # 6. 결과 요약
    stats = get_stats()
    print(f"\n{'=' * 60}")
    print("[4/4] 처리 완료")
    print(f"{'=' * 60}")
    print(f"  전체: {stats['total']}건")
    print(f"  성공: {stats['completed']}건")
    print(f"  실패: {stats['failed']}건")
    print(f"  미처리: {stats['pending']}건")


if __name__ == "__main__":
    run_pipeline()
