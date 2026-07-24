import types

import pytest

import collect_quarterly as cq

# 포스코DX(corp_code 00155212) 2024년 매출액(CFS) 실측값 — task-2-review.md §3
# H1/Q3의 thstrm_amount는 "누적"이 아니라 해당 3개월 단독값이며, 진짜 누적(YTD)은
# thstrm_add_amount에 들어있다. Q4는 FY - Q3.thstrm_add_amount로 산출한다.
POSCO_DX_2024 = {
    "Q1": {"fs_div": "CFS", "revenue": 440_116_679_815},
    "H1": {"fs_div": "CFS", "revenue": 353_016_292_156, "revenue_add": 793_132_971_971},
    "Q3": {"fs_div": "CFS", "revenue": 318_555_516_361, "revenue_add": 1_111_688_488_332},
    "FY": {"fs_div": "CFS", "revenue": 1_473_290_670_631},
}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _patch_requests(monkeypatch, payload):
    monkeypatch.setattr(cq, "requests", types.SimpleNamespace(get=lambda *a, **k: _FakeResp(payload)))
    monkeypatch.setattr(cq.time, "sleep", lambda s: None)


def test_to_quarters_posco_dx_2024_real_values():
    """리뷰 §3 실측치: Q1/Q2/Q3는 원본 thstrm_amount 그대로, Q4 = FY - Q3.thstrm_add_amount."""
    qs = {q["quarter"]: q for q in cq.to_quarters({2024: POSCO_DX_2024})}
    assert qs["2024Q1"]["revenue"] == 440_116_679_815
    assert qs["2024Q2"]["revenue"] == 353_016_292_156      # H1.thstrm_amount 그대로 (차감 없음)
    assert qs["2024Q3"]["revenue"] == 318_555_516_361      # Q3.thstrm_amount 그대로 (차감 없음)
    assert qs["2024Q4"]["revenue"] == 361_602_182_299      # FY(1,473,290,670,631) - Q3_add(1,111,688,488,332)
    assert all(qs[k]["is_cumulative"] == 0
               for k in ("2024Q1", "2024Q2", "2024Q3", "2024Q4"))


def test_to_quarters_fy_only_marks_cumulative():
    """Q1/H1/Q3 보고서가 전혀 없는 회사(FY만 공시)는 Q4=FY값 그대로, is_cumulative=1."""
    reports = {2024: {"FY": {"fs_div": "CFS", "revenue": 999_000_000, "op_income": 80_000_000}}}
    qs = cq.to_quarters(reports)
    assert len(qs) == 1
    assert qs[0]["quarter"] == "2024Q4"
    assert qs[0]["revenue"] == 999_000_000
    assert qs[0]["op_income"] == 80_000_000
    assert qs[0]["is_cumulative"] == 1


def test_to_quarters_missing_add_field_is_null_not_flagged():
    """Q3 보고서는 있지만 특정 필드의 thstrm_add_amount가 없으면 그 필드만 NULL,
    행 플래그(is_cumulative)는 OR로 오염시키지 않는다."""
    reports = {2024: {
        "Q3": {"fs_div": "CFS", "revenue": 100, "revenue_add": 300, "net_income": 10},
        "FY": {"fs_div": "CFS", "revenue": 400, "net_income": 50},
    }}
    qs = {q["quarter"]: q for q in cq.to_quarters(reports)}
    assert qs["2024Q4"]["revenue"] == 100          # 400 - 300
    assert qs["2024Q4"]["net_income"] is None      # net_income_add 없음 -> NULL
    assert qs["2024Q4"]["is_cumulative"] == 0      # Q3 보고서 자체는 있으므로 행 플래그는 오염되지 않음


def test_fetch_reports_matches_net_income_with_suffix(monkeypatch):
    """실제 DART 필드명은 '당기순이익(손실)' — startswith 매칭으로 커버되어야 함."""
    payload = {"status": "000", "list": [
        {"fs_div": "CFS", "account_nm": "매출액", "thstrm_amount": "1,000", "thstrm_add_amount": "1,000"},
        {"fs_div": "CFS", "account_nm": "영업이익", "thstrm_amount": "200", "thstrm_add_amount": "200"},
        {"fs_div": "CFS", "account_nm": "당기순이익(손실)", "thstrm_amount": "150", "thstrm_add_amount": "150"},
    ]}
    _patch_requests(monkeypatch, payload)
    out = cq.fetch_reports("00000000", 2024)
    assert out["Q1"]["revenue"] == 1000
    assert out["Q1"]["op_income"] == 200
    assert out["Q1"]["net_income"] == 150
    # interim 보고서는 thstrm_add_amount도 보관해야 함 (Q4 계산에 필요)
    assert out["H1"]["revenue_add"] == 1000
    assert out["Q3"]["net_income_add"] == 150


def test_fetch_reports_status_013_skips_quietly(monkeypatch):
    _patch_requests(monkeypatch, {"status": "013", "message": "조회된 데이터가 없습니다"})
    out = cq.fetch_reports("00000000", 2024)
    assert out == {}


def test_fetch_reports_status_limit_raises(monkeypatch):
    _patch_requests(monkeypatch, {"status": "020", "message": "요청 제한을 초과하였습니다"})
    with pytest.raises(RuntimeError):
        cq.fetch_reports("00000000", 2024)


def test_fetch_reports_status_unexpected_warns_and_skips(monkeypatch, capsys):
    _patch_requests(monkeypatch, {"status": "100", "message": "부적절한 요청"})
    out = cq.fetch_reports("00000000", 2024)
    assert out == {}
    assert "100" in capsys.readouterr().out


@pytest.mark.network
def test_fetch_reports_smoke():
    # 삼성전자 2024 연간: 매출 300조원 규모
    r = cq.fetch_reports("00126380", 2024)
    assert "FY" in r and r["FY"]["revenue"] > 2.9e14
    assert r["FY"]["net_income"] is not None
