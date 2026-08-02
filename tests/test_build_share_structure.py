import build_share_structure as bss

# 마키나락스 실측 (설계문서 §1.1). lockup_38은 38커뮤니케이션 신청기준 확약률.
MAKINA = {
    "corp_code": "01709065", "listing_date": "2026-05-20",
    "total_shares": 18_255_368, "float_pct": 38.48, "float_verdict": "confident",
    "inst_alloc": 1_626_950, "lockup_none": 29_439, "esop": 349_300,
    "lockup_15d": 83_150, "lockup_1m": 151_465,
    "lockup_3m": 520_076, "lockup_6m": 842_820, "lockup_38": 78.17,
}


def test_compute_structure_makinarocks_real_float():
    """투설 38.48%에서 확약 8.75%p를 차감하면 실유통 29.73%."""
    r = bss.compute_structure(MAKINA)
    assert r["lockup_inst"] == 1_597_511
    assert round(r["lockup_inst_pct"], 1) == 98.2       # B/기관배정
    assert round(r["free_float_pct"], 2) == 29.73
    assert r["verdict"] == "auto_ok"


def test_gate_rejects_38_exceeding_dart():
    """게이트 ④: 38 신청기준이 DART 배정기준을 초과하면 failed.

    확약기관 우선배정 구조상 신청기준이 배정기준보다 클 수 없다.
    깨지면 두 소스 중 하나가 틀렸다는 뜻이며, 유일한 외부 교차검증이다.
    """
    bad = dict(MAKINA, lockup_38=99.9)                  # 배정기준 98.2% 초과
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_gate_skipped_when_38_missing():
    """38 값 결측은 탈락 사유가 아니다 — 게이트 ④를 건너뛴다."""
    assert bss.compute_structure(dict(MAKINA, lockup_38=None))["verdict"] == "auto_ok"


def test_gate_rejects_lockup_exceeding_allocation():
    """게이트 ③: 확약이 기관배정을 넘으면 failed."""
    bad = dict(MAKINA, lockup_none=-100)                # locked > inst_alloc
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_gate_rejects_out_of_range_float():
    """게이트 ②: 실유통이 [3%, 85%] 밖이면 failed."""
    bad = dict(MAKINA, float_pct=95.0)
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_gate_rejects_ambiguous_float():
    """A 추출이 ambiguous면 추정하지 않고 failed."""
    bad = dict(MAKINA, float_verdict="ambiguous", float_pct=None)
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_na_when_no_public_offering():
    """공모 없는 상장은 na — 결측(failed)과 구분한다."""
    na = dict(MAKINA, inst_alloc=None, lockup_none=None, esop=None)
    assert bss.compute_structure(na)["verdict"] == "na"
