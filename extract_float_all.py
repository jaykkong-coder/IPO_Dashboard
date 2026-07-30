"""verify_float_extractor를 전기간(955사)에 적용해 float_extractions에 적재.

verify_float_extractor는 confident일 때만 값을 내고 애매하면 ambiguous로 빠진다
(2026-07-28 캘리브레이션: 160/172, wrong-confident 0건). 따라서 confident 판정은
추가 검증 없이 채택해도 안전하다 -- 단, 그 캘리브레이션은 2024+ 문서 172건으로만
이뤄졌다. 2016~2021 구간은 별도 골든셋(Step 7, .superpowers/sdd/...)으로 검증했고,
그 결과에 따라 LEGACY_AMBIGUOUS_GUARD 연도가 정해진다 (없으면 빈 set).
"""
import argparse
import collections

import perf_common as pc
import verify_float_extractor as vf

DDL = """CREATE TABLE IF NOT EXISTS float_extractions(
    corp_code TEXT PRIMARY KEY, float_pct REAL, verdict TEXT, detail TEXT)"""

# Step 7 골든셋 검증 결과 wrong-confident가 나온 상장연도. 해당 연도는
# extract_for_company가 confident를 반환해도 ambiguous로 강등한다.
# (verify_float_extractor.py 자체는 수정하지 않는다 -- 가드는 여기서만.)
LEGACY_AMBIGUOUS_GUARD_YEARS: set[str] = set()


def summarize(rows) -> dict:
    c = collections.Counter(r["verdict"] for r in rows)
    return {"confident": c["confident"], "ambiguous": c["ambiguous"],
            "total": len(rows)}


def run(limit=None) -> dict:
    con = pc.get_db()
    con.execute(DDL)
    rows = con.execute(
        """SELECT 회사명, dart_corp_code, 상장후주식수, 상장일 FROM ipo_companies
           WHERE (상장유형 IS NULL OR 상장유형!='SPAC')
             AND dart_corp_code IS NOT NULL
           ORDER BY 상장일""").fetchall()[:limit]
    out = []
    for i, (name, corp, total, listing_date) in enumerate(rows, 1):
        try:
            verdict, value, detail, _ = vf.extract_for_company(name, total)
        except Exception as e:
            verdict, value, detail = "ambiguous", None, f"error:{type(e).__name__}"
        year = (listing_date or "")[:4]
        if verdict == "confident" and year in LEGACY_AMBIGUOUS_GUARD_YEARS:
            verdict, value, detail = "ambiguous", None, f"era_guard_{year}:{detail}"
        con.execute(
            "INSERT OR REPLACE INTO float_extractions VALUES (?,?,?,?)",
            (corp, value, verdict, detail))
        out.append({"verdict": verdict, "value": value})
        if i % 100 == 0:
            con.commit()
            print(f"  ...{i}/{len(rows)}", flush=True)
    con.commit()
    s = summarize(out)
    print(f"confident {s['confident']}/{s['total']} "
          f"({s['confident']/max(1,s['total'])*100:.1f}%), "
          f"ambiguous {s['ambiguous']}")
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    run(ap.parse_args().limit)
