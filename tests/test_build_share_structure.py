import build_share_structure as bss

# 마키나락스 실측 (설계문서 §1.1). lockup_38은 38커뮤니케이션 신청기준 확약률.
# lockup_total은 확약표 계 행(TTOT_CNT), inst_alloc은 배정표 기관투자자 행 —
# 같은 문서의 다른 두 표에서 나온 독립된 수치이며 일치해야 한다(게이트 ③).
MAKINA = {
    "corp_code": "01709065", "listing_date": "2026-05-20",
    "total_shares": 18_255_368, "float_pct": 38.48, "float_verdict": "confident",
    "inst_alloc": 1_626_950, "lockup_total": 1_626_950, "lockup_none": 29_439,
    "esop": 349_300, "retail_alloc": 658_750,
    "lockup_15d": 83_150, "lockup_1m": 151_465,
    "lockup_3m": 520_076, "lockup_6m": 842_820, "lockup_38": 78.17,
}

# 한싹(2023-10-04) 실측. ipo_companies.상장후주식수가 상장후주식수가 아니라
# 공모주식수로 오염된 실제 사례 — 공모물량 합계가 총주식수와 정확히 일치한다
# (즉 공모 전 주식이 0주라는 뜻이 되어 성립할 수 없다).
# 게이트 ①~④를 전부 통과해 auto_ok로 나갔고 실유통 4.37%(실제 ~23%)를 보고했다.
HANSSAK = {
    "corp_code": "01602638", "listing_date": "2023-10-04",
    "total_shares": 1_500_000, "float_pct": 27.21, "float_verdict": "confident",
    "inst_alloc": 1_020_000, "lockup_total": 1_020_000, "lockup_none": 677_354,
    "esop": 105_000, "retail_alloc": 375_000,
    "lockup_15d": 5_154, "lockup_1m": 72_365,
    "lockup_3m": 223_455, "lockup_6m": 41_672, "lockup_38": 13.27,
}

# 벡트(2024-12-16) 실측. 공모비중 0.347로 게이트 ⑤ 임계값 0.5 아래 최댓값 —
# 실측 분포의 빈 구간(0.347 … 0.650)이 임계값 근거다. 정상 행이 살아남는지 고정.
VECT = {
    "corp_code": "01690147", "listing_date": "2024-12-16",
    "total_shares": 13_707_500, "float_pct": 34.7, "float_verdict": "confident",
    "inst_alloc": 3_562_500, "lockup_total": 3_562_500, "lockup_none": 3_071_679,
    "esop": 0, "retail_alloc": 1_187_500,
    "lockup_15d": 26_374, "lockup_1m": 3_093,
    "lockup_3m": 445_949, "lockup_6m": 15_405, "lockup_38": 3.12,
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
    r = bss.compute_structure(bad)
    assert r["verdict"] == "failed"
    assert r["gate"] == "4_38"


def test_gate_skipped_when_38_missing():
    """38 값 결측은 탈락 사유가 아니다 — 게이트 ④를 건너뛴다."""
    assert bss.compute_structure(dict(MAKINA, lockup_38=None))["verdict"] == "auto_ok"


def test_gate1_rejects_negative_lockup_existing():
    """게이트 ①: 보호예수 A가 음수면 failed.

    게이트 ①은 실측상 전체 탈락의 72%를 담당하는데 테스트가 없었다.
    이 fixture는 ①만 발화하도록 잡았다 — 우리사주가 투설 비유통물량보다 커서
    A가 음수가 되지만, D는 양수·[3,85] 이내이고 ③/③b/④/⑤는 모두 통과한다.
    따라서 게이트 ①을 지우면 auto_ok로 통과해 이 테스트가 깨진다.
    """
    bad = dict(MAKINA, float_pct=80.0, esop=3_700_000)
    r = bss.compute_structure(bad)
    assert r["verdict"] == "failed"
    assert r["gate"] == "1_sign"


def test_gate1_rejects_negative_inst_lockup():
    """게이트 ①: 기관확약 B가 음수면 failed (미확약 > 확약표 계).

    확약기간별 버킷을 전부 0으로 둬 ③b(합계 대조)가 건너뛰어지고,
    38 값을 비워 ④도 건너뛰어진다. ①만 남는다.
    """
    bad = dict(MAKINA, lockup_none=2_000_000, lockup_15d=0, lockup_1m=0,
               lockup_3m=0, lockup_6m=0, lockup_38=None)
    r = bss.compute_structure(bad)
    assert r["verdict"] == "failed"
    assert r["gate"] == "1_sign"


def test_gate3_rejects_lockup_total_mismatching_allocation():
    """게이트 ③: 확약표 계 != 배정표 기관배정이면 failed.

    두 표는 같은 문서 안의 독립된 표이므로 일치해야 한다. 어긋나면 둘 중 하나의
    파싱이 틀린 것이다. 버킷 합은 B와 맞춰 두어 ③b가 대신 잡지 못하게 했다 —
    ③을 지우면 이 행은 auto_ok가 되고 테스트가 깨진다.
    """
    bad = dict(MAKINA, lockup_total=1_700_000, lockup_6m=915_870)
    r = bss.compute_structure(bad)
    assert r["verdict"] == "failed"
    assert r["gate"] == "3_tables"


def test_gate3b_rejects_bucket_sum_mismatch():
    """게이트 ③b: 확약기간별 합 != B면 failed.

    확약표 계는 배정표와 일치시켜 ③이 대신 잡지 못하게 했다. 6개월 버킷만
    5,000주 어긋나므로 ③b만 발화한다.
    """
    bad = dict(MAKINA, lockup_6m=847_820)               # 합계 5,000주 초과
    r = bss.compute_structure(bad)
    assert r["verdict"] == "failed"
    assert r["gate"] == "3b_parts"


def test_gate_rejects_out_of_range_float():
    """게이트 ②: 실유통이 [3%, 85%] 밖이면 failed."""
    bad = dict(MAKINA, float_pct=95.0)
    r = bss.compute_structure(bad)
    assert r["verdict"] == "failed"
    assert r["gate"] == "2_range"


def test_gate5_rejects_offer_total_exceeding_half_of_total_shares():
    """게이트 ⑤: 공모물량이 상장예정주식수의 절반을 넘으면 failed (한싹 실측).

    공모물량 합계 = 총주식수 = 150만주. 공모 전 주식이 0주라는 뜻이 되므로
    total_shares가 상장후주식수가 아니라 공모주식수로 오염된 것이다.
    이 행은 게이트 ①~④를 전부 통과한다 — ⑤를 지우면 auto_ok가 되고
    실유통 4.37%(실제 ~23%)가 다시 분석에 흘러든다.
    """
    r = bss.compute_structure(HANSSAK)
    assert r["verdict"] == "failed"
    assert r["gate"] == "5_offer"


def test_gate5_accepts_normal_offer_ratio():
    """게이트 ⑤: 공모비중 0.347(실측 임계 아래 최댓값)은 통과해야 한다.

    임계 0.5는 실측 분포의 빈 구간(0.347 … 0.650) 한가운데다. 이 테스트가
    임계를 잘못 낮추는 변경을 막는다.
    """
    r = bss.compute_structure(VECT)
    assert r["verdict"] == "auto_ok"
    assert round(r["free_float_pct"], 2) == 31.12


def test_gate_rejects_ambiguous_float():
    """A 추출이 ambiguous면 추정하지 않고 failed."""
    bad = dict(MAKINA, float_verdict="ambiguous", float_pct=None)
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_missing_lockup_total_is_failed_not_estimated():
    """확약표 계를 못 읽었으면 기관배정으로 대체 추정하지 않고 failed.

    B = 계 − 미확약이므로 계가 없으면 B를 알 수 없다. 기관배정으로 대신 채우면
    게이트 ③이 정의상 항상 참이 되어(구 구현) 검증력이 사라진다.
    """
    bad = dict(MAKINA, lockup_total=None)
    r = bss.compute_structure(bad)
    assert r["verdict"] == "failed"
    assert r["gate"] == "0_input"


def test_na_when_no_public_offering():
    """공모 없는 상장은 na — 결측(failed)과 구분한다."""
    na = dict(MAKINA, inst_alloc=None, lockup_none=None, esop=None)
    assert bss.compute_structure(na)["verdict"] == "na"


def test_failed_not_na_when_partial_parse_leaves_both_fields_null():
    """parse_status='partial'인데 inst_alloc/lockup_none이 우연히 둘 다 null인 경우.

    impl_reports 실측에서 61건이 이 패턴이다(공모가 없어서가 아니라 파서가
    이 두 필드를 못 채운 것). row.get('inst_alloc')/('lockup_none') 둘 다 None
    이라는 이유만으로 na 처리하면 수집 실패를 '공모 없음'으로 오분류한다.
    parse_status가 명시적으로 'na'가 아닌 한 failed여야 한다.
    """
    bad = dict(MAKINA, inst_alloc=None, lockup_none=None, esop=None,
               parse_status="partial")
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_na_when_parse_status_explicitly_na():
    """impl_reports.parse_status == 'na'면 명시적으로 na."""
    na = dict(MAKINA, inst_alloc=None, lockup_none=None, esop=None,
              parse_status="na")
    assert bss.compute_structure(na)["verdict"] == "na"
