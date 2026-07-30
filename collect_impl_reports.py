"""DART 증권발행실적보고서 수집 → impl_reports.

증권발행실적보고서에는 「기관투자자 의무보유확약기간별 배정현황」이 실려 있다.
38커뮤니케이션의 확약비율(수요예측 신청수량 기준)과 달리 이 값은 배정수량 기준이며,
확약기관 우선배정 때문에 항상 신청기준보다 높다.

공모 없는 상장(코넥스 이전상장 등)은 이 보고서 자체가 없다. 결측이 아니라
개념상 해당 없음이므로 parse_status='na' 로 구분해 기록한다.
"""
import argparse
import calendar
import datetime
import io
import time
import zipfile

import requests

import impl_report_parser as irp
import perf_common as pc
from pipeline import DART_API_KEY

LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
LIMIT_STATUSES = {"020", "800"}


def _fetch_with_retry(url, params, timeout=30):
    """collect_quarterly._fetch_with_retry와 동일한 5/30/120초 백오프."""
    waits = [5, 30, 120]
    for attempt in range(4):
        try:
            return requests.get(url, params=params, timeout=timeout)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            if attempt == 3:
                raise
            print(f"[RETRY] Attempt {attempt+1} failed ({type(e).__name__}). "
                  f"Waiting {waits[attempt]}s...", flush=True)
            time.sleep(waits[attempt])


def _shift_months(y: int, m: int, d: int, delta: int) -> tuple[int, int, int]:
    """(y,m,d)에서 delta개월 이동. 대상 달에 그 날짜가 없으면 말일로 클램프.

    예: 5/31 + 1개월 → 6월은 30일까지밖에 없으므로 6/30.
    DART API는 20160631처럼 실존하지 않는 날짜를 status=100으로 거부하므로
    클램프 없이는 상장일이 29~31일인 회사의 검색 자체가 조용히 실패한다.
    """
    idx = y * 12 + (m - 1) + delta
    ny, nm = idx // 12, idx % 12 + 1
    nd = min(d, calendar.monthrange(ny, nm)[1])
    return ny, nm, nd


def search_window(listing_date: str) -> tuple[str, str]:
    """상장일 기준 4개월 전 ~ 1개월 후 (YYYYMMDD)."""
    y, m, d = (int(x) for x in listing_date.split("-"))
    by, bm, bd = _shift_months(y, m, d, -4)
    ey, em, ed = _shift_months(y, m, d, 1)
    return f"{by:04d}{bm:02d}{bd:02d}", f"{ey:04d}{em:02d}{ed:02d}"


def find_impl_report(corp_code: str, listing_date: str) -> dict | None:
    """증권발행실적보고서를 찾는다. 정정본이 있으면 접수번호가 가장 큰 것."""
    bgn, end = search_window(listing_date)
    resp = _fetch_with_retry(LIST_URL, {
        "crtfc_key": DART_API_KEY, "corp_code": corp_code,
        "bgn_de": bgn, "end_de": end, "page_count": 100})
    time.sleep(0.15)
    data = resp.json()
    status = data.get("status")
    if status in LIMIT_STATUSES:
        raise RuntimeError(
            f"DART API 한도 초과 (status={status}, msg={data.get('message')}) "
            f"corp_code={corp_code}")
    if status == "013":
        return None
    if status != "000":
        print(f"[WARN] DART status={status} corp_code={corp_code} — skip")
        return None
    items = [x for x in data.get("list", [])
             if "증권발행실적" in x.get("report_nm", "")]
    if not items:
        return None
    latest = max(items, key=lambda x: x["rcept_no"])
    return {"rcept_no": latest["rcept_no"], "report_nm": latest["report_nm"]}


def fetch_document(rcept_no: str) -> str:
    """원문 zip을 받아 첫 xml을 디코딩해 반환."""
    resp = _fetch_with_retry(DOC_URL, {
        "crtfc_key": DART_API_KEY, "rcept_no": rcept_no})
    time.sleep(0.15)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    return irp.decode_document(zf.read(zf.namelist()[0]))


def main(limit=None):
    con = pc.get_db()
    pc.ensure_tables(con)
    rows = con.execute(
        """SELECT dart_corp_code, 회사명, 상장일 FROM ipo_companies
           WHERE (상장유형 IS NULL OR 상장유형!='SPAC')
             AND dart_corp_code IS NOT NULL
           ORDER BY 상장일""").fetchall()
    done = {r[0] for r in con.execute(
        "SELECT corp_code FROM impl_reports WHERE parse_status IN ('ok','na')")}
    todo = [r for r in rows if r[0] not in done][:limit]
    print(f"대상 {len(todo)}사 (완료 {len(done)}사 스킵)")

    now = datetime.datetime.now().isoformat(timespec="seconds")
    for i, (corp, name, ld) in enumerate(todo, 1):
        found = find_impl_report(corp, ld)
        if found is None:
            con.execute(
                """INSERT OR REPLACE INTO impl_reports
                   (corp_code, parse_status, fetched_at) VALUES (?,'na',?)""",
                (corp, now))
            con.commit()
            print(f"[{i}/{len(todo)}] {name} — 실적보고서 없음(na)")
            continue
        try:
            text = fetch_document(found["rcept_no"])
            lock = irp.parse_lockup_table(text)
            alloc = irp.parse_allocation_table(text)
        except Exception as e:
            print(f"[{i}/{len(todo)}] {name} — 파싱실패: {type(e).__name__} {e}")
            con.execute(
                """INSERT OR REPLACE INTO impl_reports
                   (corp_code, rcept_no, parse_status, fetched_at)
                   VALUES (?,?,'error',?)""", (corp, found["rcept_no"], now))
            con.commit()
            continue

        status = "ok" if (lock and alloc) else "partial"
        con.execute(
            """INSERT OR REPLACE INTO impl_reports
               (corp_code, rcept_no, report_nm, inst_alloc, esop, retail_alloc,
                lockup_none, lockup_15d, lockup_1m, lockup_3m, lockup_6m,
                parse_status, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (corp, found["rcept_no"], found["report_nm"],
             (alloc or {}).get("inst"), (alloc or {}).get("esop"),
             (alloc or {}).get("retail"),
             (lock or {}).get("none"), (lock or {}).get("15d"),
             (lock or {}).get("1m"), (lock or {}).get("3m"),
             (lock or {}).get("6m"), status, now))
        con.commit()
        print(f"[{i}/{len(todo)}] {name} {status} "
              f"확약={(lock or {}).get('locked')}/{(lock or {}).get('total')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    main(ap.parse_args().limit)
