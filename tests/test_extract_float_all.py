import extract_float_all as efa


def test_summarize_counts_by_verdict():
    rows = [
        {"verdict": "confident", "value": 32.1},
        {"verdict": "confident", "value": 40.0},
        {"verdict": "ambiguous", "value": None},
    ]
    s = efa.summarize(rows)
    assert s["confident"] == 2
    assert s["ambiguous"] == 1
    assert s["total"] == 3


# --- dedupe_by_corp (Important #2: duplicate dart_corp_code rows) ---------

def test_dedupe_by_corp_keeps_earliest_listing_per_corp_code():
    """26쌍의 ipo_companies 행이 dart_corp_code를 공유한다(코넥스->코스닥
    이전상장, 사명변경 등). float_extractions는 corp_code가 PK이므로 어느
    쪽이 최종 저장되는지가 SELECT 순서에 우연히 의존해서는 안 된다 --
    "최초 신규상장이 진짜 IPO"라는 명시적 규칙으로 하나만 남긴다."""
    rows = [
        ("위세아이텍", "00374738", 850000, "2018-04-02"),
        ("위세아이텍", "00374738", 850000, "2020-02-10"),
        ("아무개", "99999999", 1000000, "2023-01-01"),
    ]
    out = efa.dedupe_by_corp(rows)
    assert len(out) == 2
    kept = {r[1]: r for r in out}
    assert kept["00374738"][3] == "2018-04-02"  # 더 이른 상장일이 살아남는다
    assert kept["99999999"][3] == "2023-01-01"


def test_dedupe_by_corp_handles_three_way_duplicate():
    """SGA시스템즈(2016)/SGA임베디드(2017)/SG(2018)처럼 corp_code가 3개
    행에 걸쳐 공유되는 경우에도 가장 이른 상장일 하나만 남아야 한다."""
    rows = [
        ("SGA시스템즈", "00963976", 2506024, "2016-03-30"),
        ("SGA임베디드", "00963976", 2506024, "2017-05-23"),
        ("SG", "00963976", 2506024, "2018-01-26"),
    ]
    out = efa.dedupe_by_corp(rows)
    assert len(out) == 1
    assert out[0][0] == "SGA시스템즈"
    assert out[0][3] == "2016-03-30"


def test_dedupe_by_corp_is_order_independent():
    """입력 순서(예: 상장일 오름차순 vs 무작위)와 무관하게 같은 결과가
    나와야 한다 -- 이전에는 SELECT ... ORDER BY 상장일로 나중에 처리되는
    행이 우연히 이전 결과를 덮어쓰는 순서 의존적 동작이었다."""
    rows_asc = [
        ("엠로", "00396925", 1016104, "2016-04-28"),
        ("엠로", "00396925", 1016104, "2021-08-13"),
    ]
    rows_desc = list(reversed(rows_asc))
    assert efa.dedupe_by_corp(rows_asc) == efa.dedupe_by_corp(rows_desc)


# --- apply_era_guard (Important #3: era guard was untested) ---------------
#
# Step 7(2016~2021, 20건) + 2022 추가검증(20건) 골든셋에서 총 3/40이
# wrong-confident였다 (대원, 에코프로비엠, 브이씨). 그 결과로 정해진
# LEGACY_AMBIGUOUS_GUARD_YEARS = {2016..2022}가 이 테스트들이 지키는 계약이다.
# 아래 discrimination 테스트는 가드 연도 집합이 비거나 축소되면 반드시
# 실패하도록 설계했다 (README: task-6-report.md의 "GUARD_TEST_DISCRIMINATION"
# 섹션에 가드를 임시로 비운 상태의 실제 pytest 실패 출력을 남겼다).

def test_era_guard_downgrades_legacy_confident_to_ambiguous():
    v, val, d = efa.apply_era_guard("confident", 45.0, "1/1_valid(table)", "2019")
    assert v == "ambiguous"
    assert val is None
    assert d == "era_guard_2019:1/1_valid(table)"  # 원래 detail이 보존된다


def test_era_guard_leaves_modern_confident_untouched():
    v, val, d = efa.apply_era_guard("confident", 45.0, "1/1_valid(table)", "2024")
    assert (v, val, d) == ("confident", 45.0, "1/1_valid(table)")


def test_era_guard_only_touches_confident_verdict():
    """ambiguous/failed 등은 연도와 무관하게 그대로 통과해야 한다 --
    가드는 "confident를 못 믿는다"는 뜻이지 "이 연도 자체가 안 된다"는
    뜻이 아니다."""
    v, val, d = efa.apply_era_guard("ambiguous", None, "0_candidates_none_valid", "2019")
    assert (v, val, d) == ("ambiguous", None, "0_candidates_none_valid")


def test_era_guard_covers_exactly_the_verified_legacy_years():
    """LEGACY_AMBIGUOUS_GUARD_YEARS가 비어있거나 2016~2022 중 한 해라도
    빠지면 이 테스트는 실패한다 (discrimination 요구사항). 2016~2022는
    골든셋에서 wrong-confident가 나온 연도(2016~2021: 대원/에코프로비엠,
    2022: 브이씨)를 포함하는 구간이고, 2023+는 별도 캘리브레이션
    (2024+ 172건, wrong-confident 0건)으로 신뢰가 확인된 구간이다."""
    guarded_years = [str(y) for y in range(2016, 2023)]
    unguarded_years = [str(y) for y in range(2023, 2027)]
    for year in guarded_years:
        v, _, _ = efa.apply_era_guard("confident", 50.0, "detail", year)
        assert v == "ambiguous", f"{year}는 강등되어야 하는데 confident로 남았다"
    for year in unguarded_years:
        v, _, _ = efa.apply_era_guard("confident", 50.0, "detail", year)
        assert v == "confident", f"{year}는 강등되면 안 되는데 ambiguous가 됐다"
