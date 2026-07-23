import pytest
import collect_quarterly as cq


def test_to_quarters_subtraction():
    reports = {2024: {
        "Q1": {"revenue": 100, "op_income": 10, "net_income": 8, "fs_div": "CFS"},
        "H1": {"revenue": 250, "op_income": 25, "net_income": 20, "fs_div": "CFS"},
        "Q3": {"revenue": 420, "op_income": 40, "net_income": 33, "fs_div": "CFS"},
        "FY": {"revenue": 600, "op_income": 55, "net_income": 45, "fs_div": "CFS"},
    }}
    qs = {q["quarter"]: q for q in cq.to_quarters(reports)}
    assert qs["2024Q2"]["revenue"] == 150
    assert qs["2024Q3"]["op_income"] == 15
    assert qs["2024Q4"]["net_income"] == 12
    assert all(q["is_cumulative"] == 0 for q in qs.values())


def test_to_quarters_missing_prior():
    reports = {2024: {"H1": {"revenue": 250, "op_income": 25,
                             "net_income": 20, "fs_div": "CFS"}}}
    qs = cq.to_quarters(reports)
    assert qs[0]["quarter"] == "2024Q2" and qs[0]["is_cumulative"] == 1


@pytest.mark.network
def test_fetch_reports_smoke():
    # 삼성전자 2024 연간: 매출 300조원 규모
    r = cq.fetch_reports("00126380", 2024)
    assert "FY" in r and r["FY"]["revenue"] > 2.9e14
