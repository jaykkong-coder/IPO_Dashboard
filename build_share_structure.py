"""impl_reports + float_extractions를 항등식으로 병합해 share_structure 적재.

    상장예정주식수 = A 보호예수 + B 기관확약 + C 우리사주 + D 실유통

투자설명서의 유통가능물량 표는 공모 전에 작성되므로 수요예측 후 확정되는
기관 확약(B)을 반영하지 못한다. 그래서 투설 유통비율은 항상 과대계상이며
과대 폭이 확약률에 비례한다. D는 여기서 B를 차감해 산출한다.
"""
import argparse
import collections
import datetime

import perf_common as pc

FLOAT_MIN, FLOAT_MAX = 3.0, 85.0
GATE3_TOL = 1               # 주 — 확약표 계와 배정표 기관배정의 허용오차
GATE4_TOL = 1.0             # %p — 38 신청기준이 배정기준을 초과할 수 있는 허용오차
GATE5_MAX_OFFER_RATIO = 0.5  # 공모물량 / 상장예정주식수 상한


def _reject(out: dict, gate: str) -> dict:
    """failed로 확정하고 어느 게이트가 잡았는지 기록. verdict는 이미 failed다."""
    out["gate"] = gate
    return out


def compute_structure(row: dict) -> dict:
    """A/B/C/D와 검증 결과를 산출. 순수 함수."""
    total = row.get("total_shares")
    out = {"corp_code": row["corp_code"], "listing_date": row.get("listing_date"),
           "total_shares": total, "lockup_existing": None, "lockup_inst": None,
           "esop": None, "free_float": None, "free_float_pct": None,
           "inst_alloc": row.get("inst_alloc"), "lockup_inst_pct": None,
           "lockup_15d": row.get("lockup_15d"), "lockup_1m": row.get("lockup_1m"),
           "lockup_3m": row.get("lockup_3m"), "lockup_6m": row.get("lockup_6m"),
           "identity_gap": None, "verdict": "failed", "gate": None,
           "evidence": row.get("float_detail")}

    inst, none_q, esop = (row.get("inst_alloc"), row.get("lockup_none"),
                          row.get("esop"))
    lockup_total = row.get("lockup_total")
    parse_status = row.get("parse_status")
    # 공모 자체가 없는 상장(이전상장 등) — 결측이 아니라 개념상 해당 없음.
    # impl_reports.parse_status가 'na'로 명시된 경우를 우선 신뢰한다.
    # parse_status가 없는 호출부(단위테스트 등)에서만 필드 결측으로 추정한다 —
    # parse_status='partial'인데 이 두 필드만 우연히 둘 다 null인 61건이 있어,
    # 그 경우까지 na로 묶으면 수집 실패(failed)를 공모 없음(na)으로 오분류한다.
    if parse_status == "na":
        out["verdict"] = "na"
        return out
    if inst is None and none_q is None and parse_status is None:
        out["verdict"] = "na"
        return out

    if (total is None or inst is None or none_q is None or esop is None
            or lockup_total is None
            or row.get("float_verdict") != "confident"
            or row.get("float_pct") is None):
        return _reject(out, "0_input")

    # B는 확약표 안에서만 계산한다(계 − 미확약). 배정표의 기관배정은 게이트 ③에서
    # 교차검증용으로만 쓴다 — B를 두 표에 걸쳐 정의하면 그 차이를 검증할 수 없다.
    b = lockup_total - none_q                  # B 기관확약
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
        return _reject(out, "1_sign")
    # ② 범위: 보호예수 비율을 유통비율로 오채택한 케이스를 걸러낸다
    if not (FLOAT_MIN <= out["free_float_pct"] <= FLOAT_MAX):
        return _reject(out, "2_range")
    # ③ 표 교차검증: 확약표의 계 == 배정표의 기관배정. 같은 문서의 서로 다른 두
    #    표에서 나온 독립된 수치이므로 어느 한쪽 파싱이 틀리면 여기서 갈라진다.
    if abs(lockup_total - inst) > GATE3_TOL:
        return _reject(out, "3_tables")
    parts = sum(row.get(k) or 0 for k in
                ("lockup_15d", "lockup_1m", "lockup_3m", "lockup_6m"))
    if parts and abs(parts - b) > 1:           # ③b 확약기간별 합 == B
        return _reject(out, "3b_parts")
    # ④ 38 교차검증: 확약기관 우선배정 구조상 신청기준 > 배정기준은 불가능.
    lk38 = row.get("lockup_38")
    if (lk38 is not None and out["lockup_inst_pct"] is not None
            and lk38 > out["lockup_inst_pct"] + GATE4_TOL):
        return _reject(out, "4_38")
    # ⑤ 공모총량 정합: 공모물량(우리사주+기관+일반)이 상장예정주식수의 절반을
    #    넘을 수는 없다. total_shares(투설/KIND)에 상장후주식수가 아니라
    #    공모주식수가 들어와 있는 오염 케이스를 DART 실적보고서로 교차검증한다.
    offer_total = ((row.get("esop") or 0) + (row.get("inst_alloc") or 0)
                   + (row.get("retail_alloc") or 0))
    if offer_total and offer_total > total * GATE5_MAX_OFFER_RATIO:
        return _reject(out, "5_offer")

    out["verdict"] = "auto_ok"
    return out


SRC_SQL = """
SELECT c.dart_corp_code AS corp_code, c.상장일 AS listing_date,
       c.상장후주식수 AS total_shares,
       c.의무보유확약비율 AS lockup_38,
       f.float_pct, f.verdict AS float_verdict, f.detail AS float_detail,
       i.inst_alloc, i.esop, i.retail_alloc, i.lockup_none, i.lockup_total,
       i.parse_status,
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
    src_rows = 0
    gates = collections.Counter()
    for r in con.execute(SRC_SQL):
        src_rows += 1
        res = compute_structure(dict(r))
        if res["gate"]:
            gates[res["gate"]] += 1
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
    # 카운트는 루프 중 누적하지 않고 커밋 후 테이블에서 다시 집계한다.
    # ipo_companies에 dart_corp_code가 중복된 행이 26건(중복분 27행) 있어
    # SRC_SQL 원행 수(src_rows)는 실제 회사 수보다 많다. share_structure는
    # corp_code가 PK라 INSERT OR REPLACE로 자동 dedupe되므로, 최종 집계는
    # 테이블 상태를 그대로 읽는 쪽이 정확하다.
    counts = dict(con.execute(
        "SELECT verdict, COUNT(*) FROM share_structure GROUP BY verdict"))
    total = sum(counts.values())
    if src_rows != total:
        print(f"[참고] 원본 SQL {src_rows}행 -> 회사 {total}사로 dedupe "
              f"(ipo_companies dart_corp_code 중복 {src_rows - total}행)")
    print(f"총 {total}사: " + ", ".join(
        f"{k}={v}({v/total*100:.1f}%)" for k, v in sorted(counts.items())))
    # 게이트별 탈락 건수 (원행 기준 — 앞선 게이트가 잡으면 뒤는 평가되지 않는다)
    print("게이트 탈락: " + ", ".join(
        f"{k}={v}" for k, v in sorted(gates.items())))


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    main()
