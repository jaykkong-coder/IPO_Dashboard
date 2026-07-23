"""DART fnlttSinglAcnt로 유니버스 분기실적 수집 → quarterly_earnings."""
import argparse
import datetime
import time

import requests

import perf_common as pc
from pipeline import DART_API_KEY

URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
REPRT = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
ACCOUNTS = {"매출액": "revenue", "영업이익": "op_income", "당기순이익": "net_income"}
SEQ = ["Q1", "H1", "Q3", "FY"]          # 누적 차감 순서
QTR_NAME = {"Q1": "Q1", "H1": "Q2", "Q3": "Q3", "FY": "Q4"}


def _parse_amount(s):
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def fetch_reports(corp_code: str, year: int) -> dict:
    out = {}
    for key, code in REPRT.items():
        resp = requests.get(URL, params={
            "crtfc_key": DART_API_KEY, "corp_code": corp_code,
            "bsns_year": str(year), "reprt_code": code}, timeout=30)
        time.sleep(0.15)
        data = resp.json()
        if data.get("status") != "000":
            continue
        acc = {}
        for fs in ("CFS", "OFS"):
            rows = [r for r in data["list"] if r.get("fs_div") == fs]
            for r in rows:
                field = ACCOUNTS.get(r.get("account_nm", "").strip())
                if field and field not in acc:
                    v = _parse_amount(r.get("thstrm_amount"))
                    if v is not None:
                        acc[field] = v
                        acc.setdefault("fs_div", fs)
            if len(acc) > 1:            # fs_div + 1개 이상 잡히면 확정
                break
        if acc:
            out[key] = acc
    return out


def to_quarters(reports_by_year: dict) -> list[dict]:
    rows = []
    for year, reports in sorted(reports_by_year.items()):
        prev_cum = None                 # 직전 보고서 누적값
        for key in SEQ:
            cur = reports.get(key)
            if cur is None:
                prev_cum = None         # 연속성 끊김 → 이후 차감 불가
                continue
            row = {"quarter": f"{year}{QTR_NAME[key]}",
                   "fs_div": cur.get("fs_div", "CFS"), "is_cumulative": 0}
            for f in ("revenue", "op_income", "net_income"):
                if key == "Q1":
                    row[f] = cur.get(f)
                elif prev_cum is not None and cur.get(f) is not None \
                        and prev_cum.get(f) is not None:
                    row[f] = cur[f] - prev_cum[f]
                else:
                    row[f] = cur.get(f)
                    row["is_cumulative"] = 1
            rows.append(row)
            prev_cum = cur
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
