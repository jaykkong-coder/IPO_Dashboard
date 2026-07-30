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
