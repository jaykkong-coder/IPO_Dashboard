"""DART fnlttSinglAcnt로 유니버스 분기실적 수집 → quarterly_earnings.

분기 산출 공식 (task-2-review.md §3 실측 근거):
    Q1 = Q1보고서(11013).thstrm_amount                         (그대로)
    Q2 = H1보고서(11012).thstrm_amount                         (그대로, 차감 없음)
    Q3 = Q3보고서(11014).thstrm_amount                         (그대로, 차감 없음)
    Q4 = FY보고서(11011).thstrm_amount - Q3보고서.thstrm_add_amount

DART 반기/3분기 보고서의 thstrm_amount는 "누적값"이 아니라 해당 3개월 단독값이다.
진짜 누적값(YTD)은 thstrm_add_amount 필드에 별도로 들어있다 (1분기만 두 필드가 우연히 같음).
"""
import argparse
import datetime
import time

import requests

import perf_common as pc
from pipeline import DART_API_KEY

URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
REPRT = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
ACCOUNTS = {"매출액": "revenue", "영업이익": "op_income"}
FIELDS = ("revenue", "op_income", "net_income")
QTR_NAME = {"Q1": "Q1", "H1": "Q2", "Q3": "Q3", "FY": "Q4"}

# DART 한도 초과류 status: 조용히 넘어가면 안 되고 즉시 중단해야 함
LIMIT_STATUSES = {"020", "800"}


def _parse_amount(s):
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _match_field(account_nm):
    name = (account_nm or "").strip()
    if name in ACCOUNTS:
        return ACCOUNTS[name]
    if name.startswith("당기순이익"):        # 실제 API 필드명 "당기순이익(손실)" 등 커버
        return "net_income"
    return None


def _fetch_with_retry(url: str, params: dict, timeout: int = 30) -> requests.Response:
    """재시도 로직을 포함한 requests.get wrapper.

    ConnectionError/Timeout 발생 시:
    - 1회차 실패: 5초 대기 후 재시도
    - 2회차 실패: 30초 대기 후 재시도
    - 3회차 실패: 120초 대기 후 재시도
    - 모두 실패: 예외 그대로 전파
    """
    waits = [5, 30, 120]
    for attempt in range(4):
        try:
            return requests.get(url, params=params, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt == 3:  # 마지막 시도
                raise
            wait_secs = waits[attempt]
            print(f"[RETRY] Attempt {attempt+1} failed ({type(e).__name__}). "
                  f"Waiting {wait_secs}s before retry...", flush=True)
            time.sleep(wait_secs)


def fetch_reports(corp_code: str, year: int) -> dict:
    """연도별 4개 보고서(Q1/H1/Q3/FY)를 조회해 원본 값을 반환.

    각 보고서(FY 제외)에 대해 `<field>`(thstrm_amount, 해당 기간 단독값)와
    `<field>_add`(thstrm_add_amount, 연초 누적값)를 함께 저장한다.
    Q4 계산 시 Q3 보고서의 `<field>_add`가 필요하다.
    """
    out = {}
    for key, code in REPRT.items():
        resp = _fetch_with_retry(URL, params={
            "crtfc_key": DART_API_KEY, "corp_code": corp_code,
            "bsns_year": str(year), "reprt_code": code}, timeout=30)
        time.sleep(0.15)
        data = resp.json()
        status = data.get("status")
        if status == "013":                 # 정상: 해당 보고서 없음
            continue
        if status in LIMIT_STATUSES:         # 한도 초과류: 조용히 넘길 수 없음
            raise RuntimeError(
                f"DART API 한도 초과 (status={status}, msg={data.get('message')}): "
                f"corp_code={corp_code} year={year} reprt_code={code}")
        if status != "000":
            print(f"[WARN] DART status={status} msg={data.get('message')} "
                  f"corp_code={corp_code} year={year} reprt_code={code} — skip")
            continue

        is_interim = key != "FY"
        acc = {}
        for fs in ("CFS", "OFS"):
            rows = [r for r in data.get("list", []) if r.get("fs_div") == fs]
            for r in rows:
                field = _match_field(r.get("account_nm"))
                if not field:
                    continue
                if field not in acc:
                    v = _parse_amount(r.get("thstrm_amount"))
                    if v is not None:
                        acc[field] = v
                        acc.setdefault("fs_div", fs)
                if is_interim:
                    add_field = f"{field}_add"
                    if add_field not in acc:
                        av = _parse_amount(r.get("thstrm_add_amount"))
                        if av is not None:
                            acc[add_field] = av
            matched = {f for f in FIELDS if f in acc}
            if matched:                      # CFS에서 핵심 지표가 하나라도 잡히면 확정
                break
        if acc:
            out[key] = acc
    return out


def to_quarters(reports_by_year: dict) -> list[dict]:
    rows = []
    for year, reports in sorted(reports_by_year.items()):
        q1, h1, q3, fy = (reports.get(k) for k in ("Q1", "H1", "Q3", "FY"))

        def _as_is_row(qname, src):
            row = {"quarter": f"{year}{qname}",
                   "fs_div": src.get("fs_div", "CFS"), "is_cumulative": 0}
            for f in FIELDS:
                row[f] = src.get(f)
            return row

        if q1:
            rows.append(_as_is_row("Q1", q1))
        if h1:
            rows.append(_as_is_row("Q2", h1))
        if q3:
            rows.append(_as_is_row("Q3", q3))

        if fy:
            if q3 is not None:
                # 정상 경로: FY 연간값 - Q3(9개월 누적, thstrm_add_amount)
                vals = {}
                for f in FIELDS:
                    fy_v, add_v = fy.get(f), q3.get(f"{f}_add")
                    vals[f] = (fy_v - add_v) if (fy_v is not None and add_v is not None) else None
                is_cumulative = 0
            else:
                # Q3 보고서 자체가 없어 차감 불가 → FY 연간값을 그대로 저장
                vals = {f: fy.get(f) for f in FIELDS}
                is_cumulative = 1
            row = {"quarter": f"{year}Q4", "fs_div": fy.get("fs_div", "CFS"),
                   "is_cumulative": is_cumulative}
            row.update(vals)
            rows.append(row)
    return rows


def main(limit=None):
    con = pc.get_db()
    pc.ensure_tables(con)
    uni = pc.load_universe(con)[:limit]
    today = datetime.date.today()
    for i, u in enumerate(uni, 1):
        corp, name = u["corp_code"], u["name"]
        start_year = int(u["listing_date"][:4]) - 1
        have = {r[0] for r in con.execute(
            "SELECT quarter FROM quarterly_earnings WHERE corp_code=?", (corp,))}
        latest2 = sorted(have)[-2:]     # 최신 2개 분기는 정정 반영 위해 재수집
        reports_by_year = {}
        for year in range(start_year, today.year + 1):
            year_quarters = {f"{year}Q{n}" for n in range(1, 5)}
            if year_quarters <= (have - set(latest2)):
                continue                # 증분: 완비된 과거 연도 스킵
            reports_by_year[year] = fetch_reports(corp, year)
        for q in to_quarters(reports_by_year):
            con.execute(
                """INSERT OR REPLACE INTO quarterly_earnings
                   (corp_code, quarter, fs_div, revenue, op_income,
                    net_income, is_cumulative) VALUES (?,?,?,?,?,?,?)""",
                (corp, q["quarter"], q["fs_div"], q["revenue"],
                 q["op_income"], q["net_income"], q["is_cumulative"]))
        con.commit()
        print(f"[{i}/{len(uni)}] {name} ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    main(ap.parse_args().limit)
