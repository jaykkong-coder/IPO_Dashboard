"""impl_reports + float_extractions를 항등식으로 병합해 share_structure 적재.

    상장예정주식수 = A 보호예수 + B 기관확약 + C 우리사주 + D 실유통

투자설명서의 유통가능물량 표는 공모 전에 작성되므로 수요예측 후 확정되는
기관 확약(B)을 반영하지 못한다. 그래서 투설 유통비율은 항상 과대계상이며
과대 폭이 확약률에 비례한다. D는 여기서 B를 차감해 산출한다.
"""
import argparse
import datetime

import perf_common as pc

FLOAT_MIN, FLOAT_MAX = 3.0, 85.0
GATE4_TOL = 1.0             # %p — 38 신청기준이 배정기준을 초과할 수 있는 허용오차


def compute_structure(row: dict) -> dict:
    """A/B/C/D와 검증 결과를 산출. 순수 함수."""
    total = row.get("total_shares")
    out = {"corp_code": row["corp_code"], "listing_date": row.get("listing_date"),
           "total_shares": total, "lockup_existing": None, "lockup_inst": None,
           "esop": None, "free_float": None, "free_float_pct": None,
           "inst_alloc": row.get("inst_alloc"), "lockup_inst_pct": None,
           "lockup_15d": row.get("lockup_15d"), "lockup_1m": row.get("lockup_1m"),
           "lockup_3m": row.get("lockup_3m"), "lockup_6m": row.get("lockup_6m"),
           "identity_gap": None, "verdict": "failed",
           "evidence": row.get("float_detail")}

    inst, none_q, esop = (row.get("inst_alloc"), row.get("lockup_none"),
                          row.get("esop"))
    # 공모 자체가 없는 상장(이전상장 등) — 결측이 아니라 개념상 해당 없음
    if inst is None and none_q is None:
        out["verdict"] = "na"
        return out

    if (total is None or inst is None or none_q is None or esop is None
            or row.get("float_verdict") != "confident"
            or row.get("float_pct") is None):
        return out

    b = inst - none_q                          # B 기관확약
    prospectus_float = row["float_pct"] / 100 * total   # 투설 유통가능 (A·C 제외분)
    a = total - prospectus_float - esop        # A 보호예수
    d = prospectus_float - b                   # D 실유통

    out.update({
        "lockup_existing": round(a), "lockup_inst": b, "esop": esop,
        "free_float": round(d), "free_float_pct": d / total * 100,
        "lockup_inst_pct": b / inst * 100 if inst else None,
    })
    # A를 역산하므로 이 값은 항상 0이다. 게이트가 아니라 기록용이며,
    # 훗날 A를 독립 추출하게 되면 그때 게이트로 승격한다.
    out["identity_gap"] = abs((a + b + esop + d) - total) / total * 100

    # ① 부호: 투설유통 < 확약이면 둘 중 하나가 틀렸다
    if a < 0 or b < 0 or d < 0:
        return out
    # ② 범위: 보호예수 비율을 유통비율로 오채택한 케이스를 걸러낸다
    if not (FLOAT_MIN <= out["free_float_pct"] <= FLOAT_MAX):
        return out
    # ③ 확약 내부 정합
    if b > inst:
        return out
    parts = sum(row.get(k) or 0 for k in
                ("lockup_15d", "lockup_1m", "lockup_3m", "lockup_6m"))
    if parts and abs(parts - b) > 1:           # 확약기간별 합 == B
        return out
    # ④ 38 교차검증: 확약기관 우선배정 구조상 신청기준 > 배정기준은 불가능.
    #    독립된 두 소스를 맞대는 유일한 외부 검증이다.
    lk38 = row.get("lockup_38")
    if (lk38 is not None and out["lockup_inst_pct"] is not None
            and lk38 > out["lockup_inst_pct"] + GATE4_TOL):
        return out

    out["verdict"] = "auto_ok"
    return out


SRC_SQL = """
SELECT c.dart_corp_code AS corp_code, c.상장일 AS listing_date,
       c.상장후주식수 AS total_shares,
       c.의무보유확약비율 AS lockup_38,
       f.float_pct, f.verdict AS float_verdict, f.detail AS float_detail,
       i.inst_alloc, i.esop, i.lockup_none,
       i.lockup_15d, i.lockup_1m, i.lockup_3m, i.lockup_6m, i.rcept_no
FROM ipo_companies c
LEFT JOIN float_extractions f ON f.corp_code = c.dart_corp_code
LEFT JOIN impl_reports i      ON i.corp_code = c.dart_corp_code
WHERE (c.상장유형 IS NULL OR c.상장유형!='SPAC') AND c.dart_corp_code IS NOT NULL
ORDER BY c.상장일
"""


def main():
    con = pc.get_db()
    pc.ensure_tables(con)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    counts = {}
    for r in con.execute(SRC_SQL):
        res = compute_structure(dict(r))
        counts[res["verdict"]] = counts.get(res["verdict"], 0) + 1
        con.execute(
            """INSERT OR REPLACE INTO share_structure
               (corp_code, listing_date, total_shares, lockup_existing,
                lockup_inst, esop, free_float, free_float_pct, inst_alloc,
                lockup_inst_pct, lockup_15d, lockup_1m, lockup_3m, lockup_6m,
                identity_gap, verdict, src_impl_rcept, src_prosp_rcept,
                evidence, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (res["corp_code"], res["listing_date"], res["total_shares"],
             res["lockup_existing"], res["lockup_inst"], res["esop"],
             res["free_float"], res["free_float_pct"], res["inst_alloc"],
             res["lockup_inst_pct"], res["lockup_15d"], res["lockup_1m"],
             res["lockup_3m"], res["lockup_6m"], res["identity_gap"],
             res["verdict"], r["rcept_no"], None, res["evidence"], now))
    con.commit()
    total = sum(counts.values())
    print(f"총 {total}사: " + ", ".join(
        f"{k}={v}({v/total*100:.1f}%)" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    main()
