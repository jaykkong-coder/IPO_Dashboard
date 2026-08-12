"""verify_float_extractor를 전기간(dart_corp_code당 1건, corp_code 중복 dedupe 후
919사)에 적용해 float_extractions에 적재.

float_extractions의 행 수(및 confident/ambiguous 카운트)는 이 919사 기준으로
재현 가능하다. run()이 SELECT하는 ipo_companies 원본 행은 946개지만 26개
corp_code가 두 행에 걸쳐 중복되므로(dedupe_by_corp), 946은 float_extractions와
1:1 대응하지 않는 숫자다 -- 최종 카운트를 인용할 때는 항상 919를 분모로 쓴다.

verify_float_extractor는 confident일 때만 값을 내고 애매하면 ambiguous로 빠진다
(2026-07-28 캘리브레이션: 160/172, wrong-confident 0건). 따라서 confident 판정은
추가 검증 없이 채택해도 안전하다 -- 단, 그 캘리브레이션은 2024+ 문서 172건으로만
이뤄졌다. 2016~2022 구간은 별도 골든셋(Step 7 + 2022 추가검증, .superpowers/sdd/
2026-07-28-share-structure-redefinition/task-6-report.md)으로 검증했고, 그
결과에 따라 LEGACY_AMBIGUOUS_GUARD_YEARS 연도가 정해진다 (없으면 빈 set).
"""
import argparse
import collections

import perf_common as pc
import verify_float_extractor as vf

DDL = """CREATE TABLE IF NOT EXISTS float_extractions(
    corp_code TEXT PRIMARY KEY, float_pct REAL, verdict TEXT, detail TEXT)"""

# Step 7 골든셋(2016~2021, 20건, confident 우선순위 float_pct>=60%)을 원문
# 대조로 수기 검증한 결과 2/20이 wrong-confident였다 (대원 81.45%->실제
# 16.29%: 표 제목행 【상장 이후 예상 유통가능물량】을 그룹라벨로 오인해
# 매도금지 소계를 유통가능으로 오채택 / 에코프로비엠 83.3%->실제 40.07%:
# 공모주식수 대비 부분비율 문구를 majority 다수결로 전체비율로 오채택).
# 0건이어야 confident를 안전하게 채택할 수 있는데 2건이 나왔으므로,
# 2016~2021 전체를 ambiguous로 강등한다 (verify_float_extractor.py 자체는
# 수정하지 않는다 -- 가드는 여기서만). 2020~2021은 Step 9에서 캐시의
# CP949 인코딩 오류를 정정해 confident 수가 급증했지만(fix_cache_encoding.py),
# 그 신규 결과들은 골든셋으로 검증된 적이 없으므로 마찬가지로 강등 대상이다.
#
# 2022 골든셋(20건, encoding fix로 새로 confident가 된 건 우선 + float_pct>=60%)도
# 별도로 검증했다. 1/20이 wrong-confident였다 (브이씨 5.4%->실제 44.2%:
# "한국투자증권(주)은 375,000주(공모 후 5.4%)를... 유통가능물량의 대거 출회를
# 방지할 목적으로... 의무보유합니다"라는, 특정 투자자 1인의 자발적 의무보유를
# 설명하는 문구가 "유통가능"이라는 단어 근처에서 4회 반복되어 majority
# 다수결로 전체비율로 오채택됨 -- 진짜 전체 유통가능비율은 표에서 44.2%로
# 확인). 2016~2021과 같은 기준(1건 이상 wrong-confident)이므로 2022도
# 강등 대상에 포함한다.
#
# data_corrections.field='유통가능주식수비율_구간검증'에 두 골든셋(2016~2021
# 20건 + 2022 20건 = 40건) 전체 근거를 기록했다.
LEGACY_AMBIGUOUS_GUARD_YEARS: set[str] = {
    "2016", "2017", "2018", "2019", "2020", "2021", "2022"}


def summarize(rows) -> dict:
    c = collections.Counter(r["verdict"] for r in rows)
    return {"confident": c["confident"], "ambiguous": c["ambiguous"],
            "total": len(rows)}


def dedupe_by_corp(rows):
    """corp_code당 정확히 하나의 행만 남긴다 -- 상장일이 가장 이른 행을
    "이 corp_code의 진짜 IPO"로 채택한다.

    ipo_companies에는 dart_corp_code를 공유하는 행이 26쌍 있다(코넥스->코스닥
    이전상장, 사명변경 등 원인이 섞여 있고 일부는 원 파이프라인의 corp_code
    매핑 자체가 의심스러운 경우도 있다 -- 예: SGA시스템즈/SGA임베디드/SG처럼
    이름이 다른 3개 행이 같은 corp_code를 공유). float_extractions는
    corp_code를 PK로 쓰므로 어차피 하나만 남는데, 예전에는 "SELECT ... ORDER
    BY 상장일" 순서상 나중에 처리되는 행이 INSERT OR REPLACE로 이전 결과를
    조용히 덮어썼다 -- 같은 캐시 문서를 다른 상장후주식수(db_total)로 두 번
    재계산 검증하면서 verdict가 뒤집힐 수 있는, 순서에 우연히 의존하는
    동작이었다. 이제는 "최초 신규상장 행이 살아남는다"는 규칙을 명시적으로
    고정해 결정적으로 만든다.

    rows: (회사명, corp_code, 상장후주식수, 상장일) 튜플 이터러블.
    반환: 상장일 오름차순으로 정렬된, corp_code당 하나씩인 튜플 리스트.
    """
    best: dict[str, tuple] = {}
    for row in rows:
        corp = row[1]
        listing_date = row[3] or ""
        cur = best.get(corp)
        if cur is None or listing_date < (cur[3] or ""):
            best[corp] = row
    return sorted(best.values(), key=lambda r: r[3] or "")


def apply_era_guard(verdict, value, detail, year):
    """confident 판정을 연도 기준으로 ambiguous로 강등한다 (Step 7 골든셋
    wrong-confident에 대응). confident가 아닌 verdict는 손대지 않는다."""
    if verdict == "confident" and year in LEGACY_AMBIGUOUS_GUARD_YEARS:
        return "ambiguous", None, f"era_guard_{year}:{detail}"
    return verdict, value, detail


def run(limit=None) -> dict:
    con = pc.get_db()
    con.execute(DDL)
    raw_rows = con.execute(
        """SELECT 회사명, dart_corp_code, 상장후주식수, 상장일 FROM ipo_companies
           WHERE (상장유형 IS NULL OR 상장유형!='SPAC')
             AND dart_corp_code IS NOT NULL
           ORDER BY 상장일""").fetchall()
    rows = dedupe_by_corp(raw_rows)[:limit]
    out = []
    for i, (name, corp, total, listing_date) in enumerate(rows, 1):
        try:
            verdict, value, detail, _ = vf.extract_for_company(name, total)
        except Exception as e:
            verdict, value, detail = "ambiguous", None, f"error:{type(e).__name__}"
        year = (listing_date or "")[:4]
        verdict, value, detail = apply_era_guard(verdict, value, detail, year)
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
