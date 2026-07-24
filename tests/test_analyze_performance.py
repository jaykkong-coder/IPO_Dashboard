import analyze_performance as ap


# --- brief 필수 3종 테스트 (그대로) ---

def test_tercile_assignment():
    vals = [10, 20, 30, 40, 50, 60]
    groups = ap.tercile(vals)
    assert groups == ["L", "L", "M", "M", "W", "W"]


def test_estimate_achievement():
    # 적용이익 100억(백만원 단위 10000), 익년 실제 순이익 80억
    r = ap.estimate_achievement(10000, {2025: 8_000_000_000}, listing_year=2024)
    assert r == 80.0
    assert ap.estimate_achievement(None, {2025: 1}, 2024) is None
    assert ap.estimate_achievement(10000, {}, 2024) is None


def test_earnings_shock():
    qs = [
        {"quarter": "2023Q3", "op_income": 100},
        {"quarter": "2023Q4", "op_income": 100},
        {"quarter": "2024Q3", "op_income": 60},   # YoY -40% → 쇼크
        {"quarter": "2024Q4", "op_income": 110},
    ]
    assert ap.earnings_shock(qs, "2024-07-01") == 1
    qs2 = [{"quarter": "2023Q3", "op_income": 100},
           {"quarter": "2024Q3", "op_income": 90}]
    assert ap.earnings_shock(qs2, "2024-07-01") == 0


# --- 데이터 보정 관련 추가 테스트 ---
# (task-5-brief "Known data facts" 대응. task-5-report.md 참고)

def test_estimate_achievement_non_per_flagged():
    """valuation_method에 'PER'이 없으면 applied_profit_mm이 순이익 지표가
    아닐 가능성이 높으므로(EV/EBITDA·PBR·PSR 등) None 처리한다."""
    r = ap.estimate_achievement(6252.87, {2025: 8_000_000_000}, 2024,
                                 valuation_method="EV/EBITDA")
    assert r is None
    # 'PER'이 부분 포함된 혼합방법은 정상 계산
    r2 = ap.estimate_achievement(10000, {2025: 8_000_000_000}, 2024,
                                  valuation_method="PER+EV/EBITDA")
    assert r2 == 80.0
    # valuation_method 미지정(None)이면 기존 동작 유지(하위호환)
    r3 = ap.estimate_achievement(10000, {2025: 8_000_000_000}, 2024)
    assert r3 == 80.0


def test_earnings_shock_skips_cumulative_scale_mismatch():
    """is_cumulative=1(Q4가 연간값 폴백)인 행과 실제 분기값 행을 직접 비교하면
    스케일이 달라 허위 쇼크가 나온다 → 두 행의 is_cumulative가 다르면 비교 보류."""
    qs = [
        {"quarter": "2023Q4", "op_income": 100000, "is_cumulative": 1},  # 연간값(폴백)
        {"quarter": "2024Q4", "op_income": 5000, "is_cumulative": 0},    # 실제 4분기 단독값
    ]
    assert ap.earnings_shock(qs, "2024-01-01") is None


def test_net_income_by_year_cumulative_fallback():
    """is_cumulative=1 Q4 행이 있으면 4분기 완비 없이도 그 값 하나를
    해당 연도 순이익으로 인정한다."""
    quarters = [
        {"quarter": "2023Q4", "net_income": 5_000_000_000, "is_cumulative": 1},
        {"quarter": "2024Q1", "net_income": 1_000_000_000, "is_cumulative": 0},
        {"quarter": "2024Q2", "net_income": 1_000_000_000, "is_cumulative": 0},
        {"quarter": "2024Q3", "net_income": 1_000_000_000, "is_cumulative": 0},
        {"quarter": "2024Q4", "net_income": 1_000_000_000, "is_cumulative": 0},
    ]
    out = ap.net_income_by_year(quarters)
    assert out[2023] == 5_000_000_000          # 폴백 단일값 인정
    assert out[2024] == 4_000_000_000          # 4분기 완비 → 합산


def test_net_income_by_year_incomplete_without_fallback_dropped():
    quarters = [
        {"quarter": "2025Q1", "net_income": 1_000_000_000, "is_cumulative": 0},
        {"quarter": "2025Q2", "net_income": None, "is_cumulative": 0},
    ]
    out = ap.net_income_by_year(quarters)
    assert 2025 not in out


def test_revenue_yoy_2q():
    qs = [
        {"quarter": "2023Q3", "revenue": 100, "is_cumulative": 0},
        {"quarter": "2023Q4", "revenue": 100, "is_cumulative": 0},
        {"quarter": "2024Q3", "revenue": 150, "is_cumulative": 0},  # +50%
        {"quarter": "2024Q4", "revenue": 120, "is_cumulative": 0},  # +20%
    ]
    assert ap.revenue_yoy_2q(qs, "2024-07-01") == 35.0  # median(50,20)
    assert ap.revenue_yoy_2q([], "2024-07-01") is None
