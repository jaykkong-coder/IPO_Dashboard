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
import re
import time
import zipfile

import requests

import impl_report_parser as irp
import perf_common as pc
from pipeline import DART_API_KEY

LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
LIMIT_STATUSES = {"020", "800"}
_XML_STATUS_RE = re.compile(r"<status>\s*([^<\s]+)\s*</status>", re.I)


class DartStatusError(Exception):
    """DART가 000/013이 아닌 status를 돌려줬다 — 공모 없음(na)과는 다른 사건.

    RuntimeError를 상속하지 않는다. 한도류(RuntimeError)는 실행을 중단시켜야 하고,
    이쪽은 회사별 error로 기록해 다음 실행에서 재시도해야 하기 때문이다.
    """


def _status_from_body(resp) -> str | None:
    """에러 응답 본문(JSON 또는 XML)에서 status 코드를 뽑는다."""
    try:
        return resp.json().get("status")
    except ValueError:
        pass
    m = _XML_STATUS_RE.search(resp.text)
    return m.group(1) if m else None


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
    """증권발행실적보고서를 찾는다. 정정본이 있으면 접수번호가 가장 큰 것.

    None은 오직 "공모가 없어 보고서가 존재하지 않는다"만 뜻한다(→ na).
    한도류는 RuntimeError로 즉시 중단하고, 그 밖의 비정상 status도 RuntimeError로
    올려 보내 호출부가 error로 기록·재시도하게 한다. na는 재시도 대상이 아니므로
    API 이상을 na로 적으면 영구히 되돌릴 수 없다.
    """
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
    if status == "013":                      # 정상: 조회 결과 없음
        return None
    if status != "000":
        raise DartStatusError(
            f"DART list.json 비정상 status={status} "
            f"msg={data.get('message')} corp_code={corp_code}")
    items = [x for x in data.get("list", [])
             if "증권발행실적" in x.get("report_nm", "")]
    if not items:
        return None
    latest = max(items, key=lambda x: x["rcept_no"])
    return {"rcept_no": latest["rcept_no"], "report_nm": latest["report_nm"]}


def fetch_document(rcept_no: str) -> str:
    """원문 zip을 받아 첫 xml을 디코딩해 반환.

    document.xml은 정상일 때 zip 바이너리를 돌려주지만, 한도 초과·키 오류 등에는
    JSON/XML 에러 본문을 돌려준다. 그대로 unzip하면 BadZipFile이 나고 호출부의
    광범위한 except가 이를 회사별 '파싱실패'로 적어버린다 — 한도 벽에 부딪힌 뒤
    남은 전량이 조용히 오분류된다. 압축을 풀기 전에 본문을 먼저 확인한다.
    """
    resp = _fetch_with_retry(DOC_URL, {
        "crtfc_key": DART_API_KEY, "rcept_no": rcept_no})
    time.sleep(0.15)
    ctype = resp.headers.get("content-type", "").lower()
    if ctype.startswith(("application/json", "text/")):
        status = _status_from_body(resp)
        if status in LIMIT_STATUSES:
            raise RuntimeError(
                f"DART API 한도 초과 (status={status}) rcept_no={rcept_no}")
        raise DartStatusError(
            f"DART document.xml 비정상 응답 (status={status}) "
            f"rcept_no={rcept_no}: {resp.text[:200]}")
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
    # 재개 규칙: 종결 상태(ok/na)는 건너뛴다. 단 ok 행이라도 현재 스키마의
    # lockup_total이 비어 있으면(열 추가 이전에 수집된 행) 다시 받는다.
    # 재수집하면 반드시 채워지는 값이라 이 조건은 한 번 돌면 수렴한다.
    done = {r[0] for r in con.execute(
        """SELECT corp_code FROM impl_reports
           WHERE parse_status='na'
              OR (parse_status='ok' AND lockup_total IS NOT NULL)""")}
    todo = [r for r in rows if r[0] not in done][:limit]
    print(f"대상 {len(todo)}사 (완료 {len(done)}사 스킵)")

    now = datetime.datetime.now().isoformat(timespec="seconds")
    for i, (corp, name, ld) in enumerate(todo, 1):
        found = None
        try:
            found = find_impl_report(corp, ld)
            if found is None:
                con.execute(
                    """INSERT OR REPLACE INTO impl_reports
                       (corp_code, parse_status, fetched_at)
                       VALUES (?,'na',?)""", (corp, now))
                con.commit()
                print(f"[{i}/{len(todo)}] {name} — 실적보고서 없음(na)")
                continue
            text = fetch_document(found["rcept_no"])
            lock = irp.parse_lockup_table(text)
            alloc = irp.parse_allocation_table(text)
        except RuntimeError:
            # 한도 초과류 — 남은 전량을 오분류하며 소진시키지 않도록 즉시 중단한다.
            raise
        except Exception as e:
            print(f"[{i}/{len(todo)}] {name} — 파싱실패: {type(e).__name__} {e}")
            con.execute(
                """INSERT OR REPLACE INTO impl_reports
                   (corp_code, rcept_no, parse_status, fetched_at)
                   VALUES (?,?,'error',?)""",
                (corp, (found or {}).get("rcept_no"), now))
            con.commit()
            continue

        status = "ok" if (lock and alloc) else "partial"
        con.execute(
            """INSERT OR REPLACE INTO impl_reports
               (corp_code, rcept_no, report_nm, inst_alloc, esop, retail_alloc,
                lockup_none, lockup_total, lockup_15d, lockup_1m, lockup_3m,
                lockup_6m, parse_status, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (corp, found["rcept_no"], found["report_nm"],
             (alloc or {}).get("inst"), (alloc or {}).get("esop"),
             (alloc or {}).get("retail"),
             (lock or {}).get("none"), (lock or {}).get("total"),
             (lock or {}).get("15d"),
             (lock or {}).get("1m"), (lock or {}).get("3m"),
             (lock or {}).get("6m"), status, now))
        con.commit()
        print(f"[{i}/{len(todo)}] {name} {status} "
              f"확약={(lock or {}).get('locked')}/{(lock or {}).get('total')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    main(ap.parse_args().limit)
