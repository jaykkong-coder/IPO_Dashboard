"""
기존 다운로드된 문서를 재파싱하여 DB 업데이트 (네트워크 불필요)
"""

import os
import sqlite3
from kind_scraper import get_kind_ipo_list
from ipo_extractor import extract_ipo_data
from database import init_db, upsert_company, get_stats

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
SPAC_KEYWORDS = ["스팩", "SPAC", "기업인수목적"]


def is_spac(company):
    combined = f"{company.get('회사명', '')} {company.get('주요제품', '')} {company.get('업종', '')}"
    return any(kw in combined for kw in SPAC_KEYWORDS)


def is_merger(company_name):
    """투자설명서 앞부분에 '합병' 키워드가 있으면 합병상장"""
    import re
    doc_dir = os.path.join(DOCS_DIR, company_name)
    if not os.path.isdir(doc_dir):
        return False
    for fname in os.listdir(doc_dir):
        if not fname.endswith((".xml", ".html", ".htm")):
            continue
        with open(os.path.join(doc_dir, fname), "r", encoding="utf-8", errors="replace") as f:
            text = f.read(5000)
        clean = re.sub(r"<[^>]+>", " ", text)
        if "합병" in clean[:2000]:
            return True
        break
    return False


def run():
    init_db()

    # KIND 목록
    print("[1/3] KIND 목록 수집...")
    kosdaq = get_kind_ipo_list(start_date="2025-01-01", market_type="kosdaqMkt")
    kospi = get_kind_ipo_list(start_date="2025-01-01", market_type="stockMkt")
    all_companies = kosdaq + kospi
    print(f"  코스닥: {len(kosdaq)}건, 유가증권: {len(kospi)}건")

    # SPAC & 합병상장 등록
    for c in all_companies:
        if is_spac(c):
            c["처리상태"] = "skipped"
            c["처리메모"] = "SPAC"
            upsert_company(c)
        elif is_merger(c["회사명"]):
            c["처리상태"] = "skipped"
            c["처리메모"] = "합병상장"
            upsert_company(c)

    # 문서 재파싱
    print("[2/3] 기존 문서 재파싱...")
    success = 0
    fail = 0

    non_spac = [c for c in all_companies if not is_spac(c) and not is_merger(c["회사명"])]
    for i, company in enumerate(non_spac):
        name = company["회사명"]
        doc_dir = os.path.join(DOCS_DIR, name)

        if not os.path.exists(doc_dir):
            company["처리상태"] = "failed"
            company["처리메모"] = "문서 없음"
            upsert_company(company)
            fail += 1
            continue

        # XML/HTML 파일 찾기
        doc_files = [f for f in os.listdir(doc_dir) if f.endswith((".xml", ".html", ".htm"))]
        if not doc_files:
            company["처리상태"] = "failed"
            company["처리메모"] = "파싱 가능 파일 없음"
            upsert_company(company)
            fail += 1
            continue

        filepath = os.path.join(doc_dir, doc_files[0])
        try:
            ipo_data = extract_ipo_data(filepath)
            # KIND 데이터 우선 (시장구분은 KIND에서)
            ipo_data.pop("시장구분", None)
            ipo_data.pop("상장유형_from_extractor", None)

            merged = {**company, **ipo_data}
            # 상장유형: extractor 결과를 사용하되, None이면 KIND 시장구분으로는 대체 안함
            merged["처리상태"] = "completed"
            upsert_company(merged)

            extracted = sum(1 for k, v in ipo_data.items() if v is not None and v != 0)
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(non_spac)}] {name}: {extracted}개 필드")
            success += 1
        except Exception as e:
            company["처리상태"] = "failed"
            company["처리메모"] = str(e)[:100]
            upsert_company(company)
            fail += 1

    # 이상값 정리
    print("[3/3] 이상값 정리...")
    conn = sqlite3.connect(os.path.join(BASE_DIR, "ipo_data.db"))
    c = conn.cursor()
    c.execute("UPDATE ipo_companies SET 평가방법 = NULL WHERE 평가방법 IS NOT NULL AND LENGTH(평가방법) > 15")
    c.execute("UPDATE ipo_companies SET 평가방법 = NULL WHERE 평가방법 IN ('④', '⑤', '이항모형', '구  분', 'CE(유럽)', '1')")
    c.execute("UPDATE ipo_companies SET 공모비율 = NULL WHERE 공모비율 > 50")
    c.execute("UPDATE ipo_companies SET 기준시가총액_억원 = NULL WHERE 기준시가총액_억원 > 100000")
    c.execute("UPDATE ipo_companies SET 할인율_하단 = NULL, 할인율_상단 = NULL WHERE 할인율_하단 IS NOT NULL AND 할인율_하단 > 80")
    c.execute("UPDATE ipo_companies SET 적정시가총액_억원 = NULL WHERE 적정시가총액_억원 IS NOT NULL AND 적정시가총액_억원 > 500000")
    conn.commit()

    # 결과
    print(f"\n성공: {success}건, 실패: {fail}건")

    for label, sql in [
        ("시장구분", "SELECT 시장구분, COUNT(*) FROM ipo_companies WHERE 처리상태='completed' GROUP BY 시장구분"),
        ("상장유형", "SELECT COALESCE(상장유형,'(미분류)'), COUNT(*) FROM ipo_companies WHERE 처리상태='completed' GROUP BY 상장유형 ORDER BY COUNT(*) DESC"),
        ("평가방법", "SELECT COALESCE(평가방법,'(없음)'), COUNT(*) FROM ipo_companies WHERE 처리상태='completed' GROUP BY 평가방법 ORDER BY COUNT(*) DESC"),
        ("공모가위치", "SELECT COALESCE(공모가최종,'(없음)'), COUNT(*) FROM ipo_companies WHERE 처리상태='completed' GROUP BY 공모가최종 ORDER BY COUNT(*) DESC"),
    ]:
        print(f"\n{label}:")
        for m, cnt in c.execute(sql).fetchall():
            print(f"  {m}: {cnt}건")

    # None 필드 현황
    total = c.execute("SELECT COUNT(*) FROM ipo_companies WHERE 처리상태='completed'").fetchone()[0]
    print(f"\nNone 필드 현황 ({total}건 중 채워진 수):")
    for f in ['대표주관회사','평가방법','적용멀티플','할인율_하단','확정공모가','기준시가총액_억원','공모비율','유통가능주식수비율','인수수수료총액_억원','신주','상장유형']:
        cnt = c.execute(f"SELECT COUNT(*) FROM ipo_companies WHERE 처리상태='completed' AND {f} IS NOT NULL").fetchone()[0]
        print(f"  {f:25s}: {cnt}/{total}")

    conn.close()


if __name__ == "__main__":
    run()
