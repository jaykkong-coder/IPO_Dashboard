"""그룹핑·요인 대조 통계 → analysis_flags + analysis_output.json.

데이터 보정 (task-5-brief "Known data facts" 대응, task-5-report.md 참고):

1. net_income_by_year(): quarterly_earnings에 is_cumulative=1인 Q4 행이 있으면
   4분기 완비 요구 없이 그 값 하나를 해당 연도 순이익으로 인정한다(FY-only 보완).
   실측 결과 이 보정은 listing_year+1(추정치 달성률 산출 대상 연도)에는 영향이
   없었다 — is_cumulative=1은 상장 전 연도(주로 listing_year-1)에서만 나타나며,
   상장 다음 해는 항상 실제 4분기 데이터가 존재했다. 그래도 향후 데이터 갱신에
   대한 방어적 보정으로 유지한다.
2. estimate_achievement(): valuation_method 문자열에 'PER'이 없으면
   applied_profit_mm이 순이익이 아닌 다른 지표(EV/EBITDA·PBR·PSR 등)일 가능성이
   높으므로 None 처리한다(실측 25개사 영향, 아래 리포트 참고).
3. earnings_shock() / revenue_yoy_2q(): 비교하는 두 분기 행 중 하나만
   is_cumulative=1(연간값 폴백)이면 스케일이 달라(연간 vs 분기) 왜곡되므로
   비교를 보류(skip)한다.
"""
import datetime
import json
import statistics

import perf_common as pc

SHOCK_THRESHOLD = -30.0          # 영업이익 YoY %


def tercile(values: list) -> list[str]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    n = len(values)
    cut_l, cut_w = n / 3, 2 * n / 3
    out = [""] * n
    for rank, i in enumerate(order):
        out[i] = "L" if rank < cut_l else ("W" if rank >= cut_w else "M")
    return out


def estimate_achievement(applied_profit_mm, actual_net_by_year, listing_year,
                          valuation_method=None):
    if not applied_profit_mm:
        return None
    if valuation_method is not None and "PER" not in valuation_method:
        return None
    actual = actual_net_by_year.get(listing_year + 1)
    if actual is None:
        return None
    return round(actual / (applied_profit_mm * 1e6) * 100, 1)


def _prev_year_q(q):
    return f"{int(q[:4]) - 1}{q[4:]}"


def _listing_quarter(listing_date):
    return f"{listing_date[:4]}Q{(int(listing_date[5:7]) - 1) // 3 + 1}"


def _first_2q_after_listing(by_q, listing_date):
    # 상장 분기 자체를 포함해야 brief Step1 테스트("2024-07-01" 상장 →
    # 2024Q3 op_income YoY -40%가 쇼크로 잡혀야 함)를 만족한다. '>' 로는
    # 상장 분기가 배제되어 원 브리프 테스트조차 통과하지 못했다(실측 확인).
    listing_q = _listing_quarter(listing_date)
    return sorted(q for q in by_q if q >= listing_q)[:2]


def earnings_shock(quarters, listing_date):
    by_q = {q["quarter"]: q for q in quarters}
    after = _first_2q_after_listing(by_q, listing_date)
    compared = 0
    for q in after:
        cur_row = by_q[q]
        prev_row = by_q.get(_prev_year_q(q), {})
        cur, prev = cur_row.get("op_income"), prev_row.get("op_income")
        if cur is None or prev is None or prev <= 0:
            continue
        if cur_row.get("is_cumulative") != prev_row.get("is_cumulative"):
            continue  # 연간값(폴백) vs 분기값 스케일 불일치 → 비교 보류
        compared += 1
        yoy = (cur / prev - 1) * 100
        if yoy <= SHOCK_THRESHOLD or cur < 0:
            return 1
    return 0 if compared else None


def revenue_yoy_2q(quarters, listing_date):
    """상장 후 첫 2개 분기 매출 YoY(%) 중앙값. 비교쌍 없으면 None."""
    by_q = {q["quarter"]: q for q in quarters}
    after = _first_2q_after_listing(by_q, listing_date)
    yoys = []
    for q in after:
        cur_row = by_q[q]
        prev_row = by_q.get(_prev_year_q(q), {})
        cur, prev = cur_row.get("revenue"), prev_row.get("revenue")
        if cur is None or prev is None or prev <= 0:
            continue
        if cur_row.get("is_cumulative") != prev_row.get("is_cumulative"):
            continue
        yoys.append((cur / prev - 1) * 100)
    return round(statistics.median(yoys), 1) if yoys else None


def net_income_by_year(quarters):
    """연간 순이익 매핑. 4분기 완비 시 합산, is_cumulative=1인 Q4(연간값
    폴백)가 있으면 그 값 하나로 해당 연도 순이익을 인정."""
    by_year = {}
    cumulative = {}
    for q in quarters:
        y = int(q["quarter"][:4])
        by_year.setdefault(y, []).append(q["net_income"])
        if q.get("is_cumulative"):
            cumulative[y] = q["net_income"]
    out = {}
    for y, vals in by_year.items():
        if y in cumulative and cumulative[y] is not None:
            out[y] = cumulative[y]
        elif len(vals) == 4 and all(v is not None for v in vals):
            out[y] = sum(vals)
    return out


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _rate_pct(xs):
    """0/1 이진 변수의 비율(%). earnings_shock처럼 드문 이벤트는 median이
    아니라 비율로 봐야 W/L 차이가 드러난다."""
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs) * 100, 1) if xs else None


FACTORS = ["float_ratio", "inst_ratio", "lockup_ratio", "offer_size",
           "price_vs_band_top", "old_share_ratio", "estimate_achievement",
           "earnings_shock", "revenue_yoy_2q"]
FACTOR_STAT = {"earnings_shock": _rate_pct}


def main():
    con = pc.get_db()
    pc.ensure_tables(con)
    tickers = pc.corp_to_stock_map()
    uni = pc.load_universe(con)
    # --- 종목별 데이터 조립
    rows = []
    for u in uni:
        code = tickers.get(u["corp_code"])
        if not code:
            continue
        perf = {}
        for r in con.execute(
                """SELECT horizon, abs_return, excess_return FROM price_performance
                   WHERE stock_code=? AND base_price_type='IPO'""", (code,)):
            perf[r["horizon"]] = {"abs": r["abs_return"], "excess": r["excess_return"]}
        quarters = [dict(r) for r in con.execute(
            """SELECT quarter, op_income, net_income, revenue, is_cumulative
               FROM quarterly_earnings WHERE corp_code=? ORDER BY quarter""",
            (u["corp_code"],))]
        net_by_year = net_income_by_year(quarters)
        ly = int(u["listing_date"][:4])
        new_s, old_s = u["new_shares"] or 0, u["old_shares"] or 0
        rows.append({**u, "stock_code": code, "perf": perf,
                     "estimate_achievement": estimate_achievement(
                         u["applied_profit_mm"], net_by_year, ly,
                         u["valuation_method"]),
                     "earnings_shock": earnings_shock(quarters, u["listing_date"]),
                     "revenue_yoy_2q": revenue_yoy_2q(quarters, u["listing_date"]),
                     "old_share_ratio": round(old_s / (new_s + old_s) * 100, 1)
                     if (new_s + old_s) else None})
    # --- 지평별 tercile (IPO 기준 excess_return)
    groups_by_h = {}
    for h in ("1M", "3M", "6M", "12M"):
        sub = [r for r in rows if r["perf"].get(h, {}).get("excess") is not None]
        labels = tercile([r["perf"][h]["excess"] for r in sub])
        for r, g in zip(sub, labels):
            r.setdefault("groups", {})[h] = g
        groups_by_h[h] = sub
    # --- 업종 내 상대성과 (6M)
    by_ind = {}
    for r in groups_by_h["6M"]:
        by_ind.setdefault(r["industry"], []).append(r["perf"]["6M"]["excess"])
    ind_median = {k: statistics.median(v) for k, v in by_ind.items()}
    overall_median_6m = statistics.median(
        [r["perf"]["6M"]["excess"] for r in groups_by_h["6M"]])
    for r in groups_by_h["6M"]:
        r["industry_relative_6m"] = round(
            r["perf"]["6M"]["excess"] - ind_median[r["industry"]], 1)
    # --- analysis_flags 저장
    for r in rows:
        con.execute(
            """INSERT OR REPLACE INTO analysis_flags VALUES (?,?,?,?,?,?)""",
            (r["stock_code"], r["corp_code"], r.get("groups", {}).get("6M"),
             r["estimate_achievement"], r["earnings_shock"],
             r.get("industry_relative_6m")))
    con.commit()
    # --- factor_contrast
    contrast = []
    six = groups_by_h["6M"]
    for f in FACTORS:
        stat = FACTOR_STAT.get(f, _median)
        w = stat([r[f] for r in six if r["groups"]["6M"] == "W"])
        l = stat([r[f] for r in six if r["groups"]["6M"] == "L"])
        if w is None or l is None:
            continue
        direction = w > l
        consistent = []
        for h, sub in groups_by_h.items():
            wh = stat([r[f] for r in sub if r["groups"][h] == "W"])
            lh = stat([r[f] for r in sub if r["groups"][h] == "L"])
            if wh is not None and lh is not None and (wh > lh) == direction:
                consistent.append(h)
        contrast.append({"factor": f, "W_median": w, "L_median": l,
                         "W_n": sum(1 for r in six if r["groups"]["6M"] == "W"),
                         "L_n": sum(1 for r in six if r["groups"]["6M"] == "L"),
                         "consistent_horizons": consistent})
    # --- 산출
    out = {
        "meta": {"asof": datetime.date.today().isoformat(),
                 "universe_n": len(uni), "grouped_n": len(six)},
        "horizon_summary": {
            h: {"n": len(sub),
                "median_abs": _median([r["perf"][h]["abs"] for r in sub]),
                "median_excess": _median([r["perf"][h]["excess"] for r in sub])}
            for h, sub in groups_by_h.items()},
        "groups_6m": {g: {"n": sum(1 for r in six if r["groups"]["6M"] == g),
                          "median_excess": _median(
                              [r["perf"]["6M"]["excess"] for r in six
                               if r["groups"]["6M"] == g])}
                      for g in ("W", "M", "L")},
        "factor_contrast": contrast,
        # 주의: median_industry_relative는 "업종 자체 중앙값 대비 전체 유니버스
        # 중앙값" 차이다. 업종별로 자기 업종 중앙값을 빼면(즉 industry_relative_6m을
        # 업종 내에서 다시 median 내면) 정의상 항상 0이 되므로(분포를 그 분포의
        # median만큼 평행이동하면 새 median은 항상 0) 그 방식은 배제했다.
        "industry_table": [
            {"industry": k, "n": len(v),
             "median_excess_6m": round(statistics.median(v), 1),
             "median_industry_relative": round(
                 statistics.median(v) - overall_median_6m, 1)}
            for k, v in sorted(by_ind.items(), key=lambda x: -len(x[1]))],
        "companies": [
            {"name": r["name"], "stock_code": r["stock_code"],
             "industry": r["industry"],
             "group_6m": r.get("groups", {}).get("6M"),
             "excess_6m": r["perf"].get("6M", {}).get("excess"),
             "float_ratio": r["float_ratio"],
             "estimate_achievement": r["estimate_achievement"],
             "earnings_shock": r["earnings_shock"]} for r in rows],
    }
    with open(pc.ROOT / "analysis_output.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"grouped {len(six)} / universe {len(uni)} → analysis_output.json")


if __name__ == "__main__":
    main()
