from pathlib import Path

import impl_report_parser as irp

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# 마키나락스 증권발행실적보고서(20260514001096) 실측 — 확약 우선배정 제도 시행 후
MAKINA_TABLE = """
<TABLE>
<TR><TD>확약기간</TD><TD>운용사(집합)</TD><TD>비중</TD><TD>합계</TD><TD>비중</TD></TR>
<TR><TD>15일 확약</TD><TD>26,458</TD><TD>2.1</TD><TD>83,150</TD><TD>5.1</TD></TR>
<TR><TD>1개월 확약</TD><TD>81,662</TD><TD>6.5</TD><TD>151,465</TD><TD>9.3</TD></TR>
<TR><TD>3개월 확약</TD><TD>458,664</TD><TD>36.3</TD><TD>520,076</TD><TD>32.0</TD></TR>
<TR><TD>6개월 확약</TD><TD>694,227</TD><TD>54.9</TD><TD>842,820</TD><TD>51.8</TD></TR>
<TR><TD>미확약</TD><TD>3,508</TD><TD>0.3</TD><TD>29,439</TD><TD>1.8</TD></TR>
<TR><TD>계</TD><TD>1,264,519</TD><TD>100.0</TD><TD>1,626,950</TD><TD>100.0</TD></TR>
</TABLE>
"""

# 토모큐브(20241031000452) 실측 — 2024년 하반기 저확약 국면, '2주일 확약' 표기
TOMO_TABLE = """
<TABLE>
<TR><TD>확약기간</TD><TD>운용사(집합)</TD><TD>비중</TD><TD>합계</TD><TD>비중</TD></TR>
<TR><TD>6개월 확약</TD><TD>-</TD><TD>-</TD><TD>1,723</TD><TD>0.11</TD></TR>
<TR><TD>3개월 확약</TD><TD>-</TD><TD>-</TD><TD>16,106</TD><TD>1.07</TD></TR>
<TR><TD>1개월 확약</TD><TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD></TR>
<TR><TD>2주일 확약</TD><TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD></TR>
<TR><TD>미확약</TD><TD>249,016</TD><TD>100</TD><TD>1,482,171</TD><TD>98.81</TD></TR>
<TR><TD>계</TD><TD>249,016</TD><TD>100</TD><TD>1,500,000</TD><TD>100</TD></TR>
</TABLE>
"""

# 2주일 확약 매핑 검증용 fixture — '2주일 확약' 행에 nonzero 수량 포함
TWO_WEEKS_TABLE = """
<TABLE>
<TR><TD>확약기간</TD><TD>운용사(집합)</TD><TD>비중</TD><TD>합계</TD><TD>비중</TD></TR>
<TR><TD>6개월 확약</TD><TD>50,000</TD><TD>10.0</TD><TD>100,000</TD><TD>20.0</TD></TR>
<TR><TD>3개월 확약</TD><TD>40,000</TD><TD>8.0</TD><TD>80,000</TD><TD>16.0</TD></TR>
<TR><TD>1개월 확약</TD><TD>30,000</TD><TD>6.0</TD><TD>60,000</TD><TD>12.0</TD></TR>
<TR><TD>2주일 확약</TD><TD>60,000</TD><TD>12.0</TD><TD>120,000</TD><TD>24.0</TD></TR>
<TR><TD>미확약</TD><TD>50,000</TD><TD>10.0</TD><TD>140,000</TD><TD>28.0</TD></TR>
<TR><TD>계</TD><TD>230,000</TD><TD>46.0</TD><TD>500,000</TD><TD>100.0</TD></TR>
</TABLE>
"""


def test_parse_lockup_table_makinarocks():
    """확약 우선배정 시행 후 사례: 미확약 1.8% → 확약 98.2%."""
    r = irp.parse_lockup_table(MAKINA_TABLE)
    assert r["total"] == 1_626_950
    assert r["none"] == 29_439
    assert r["15d"] == 83_150
    assert r["1m"] == 151_465
    assert r["3m"] == 520_076
    assert r["6m"] == 842_820
    assert r["locked"] == 1_597_511          # total - none


def test_parse_lockup_table_tomocube_treats_2weeks_as_15d():
    """'2주일 확약'은 '15일 확약'과 같은 범주로 통합한다. 빈칸('-')은 0."""
    r = irp.parse_lockup_table(TOMO_TABLE)
    assert r["total"] == 1_500_000
    assert r["none"] == 1_482_171
    assert r["6m"] == 1_723
    assert r["3m"] == 16_106
    assert r["1m"] == 0
    assert r["15d"] == 0
    assert r["locked"] == 17_829


def test_parse_lockup_table_returns_none_when_absent():
    assert irp.parse_lockup_table("<TABLE><TR><TD>무관한표</TD></TR></TABLE>") is None


def test_lockup_components_sum_to_total():
    """확약기간별 합 + 미확약 = 계. 열 선택이 틀리면 여기서 깨진다."""
    for table in (MAKINA_TABLE, TOMO_TABLE):
        r = irp.parse_lockup_table(table)
        parts = r["15d"] + r["1m"] + r["3m"] + r["6m"] + r["none"]
        assert parts == r["total"], f"{parts} != {r['total']}"


def test_parse_lockup_table_2weeks_alias_maps_to_15d():
    """'2주일 확약' 라벨이 '15일 확약'과 같은 범주로 '15d' 키로 매핑됨을 검증.

    이 테스트는 nonzero '2주일 확약' 수량을 포함해야 매핑 유무를 구분할 수 있다.
    """
    r = irp.parse_lockup_table(TWO_WEEKS_TABLE)
    assert r["15d"] == 120_000, "2주일 확약 수량이 15d 키로 매핑되어야 함"
    assert r["6m"] == 100_000
    assert r["3m"] == 80_000
    assert r["1m"] == 60_000
    assert r["none"] == 140_000
    assert r["total"] == 500_000
    # 내부 정합성: 모든 확약기간의 합 = total
    parts = r["15d"] + r["1m"] + r["3m"] + r["6m"] + r["none"]
    assert parts == r["total"]


def test_decode_document_prefers_utf8():
    raw = "의무보유확약".encode("utf-8")
    assert irp.decode_document(raw) == "의무보유확약"


def test_decode_document_falls_back_to_cp949():
    """2022년 이전 DART 문서는 EUC-KR(cp949)이다."""
    raw = "의무보유확약".encode("cp949")
    assert irp.decode_document(raw) == "의무보유확약"


def test_parse_qty():
    assert irp.parse_qty("1,626,950") == 1626950
    assert irp.parse_qty("0") == 0
    assert irp.parse_qty("-") is None
    assert irp.parse_qty("") is None
    assert irp.parse_qty("5.1") is None          # 비중은 수량이 아니다


def test_extract_rows_parses_table_cells():
    text = """
    <TABLE><TR><TD>15일 확약</TD><TD>26,458</TD><TD>2.1</TD></TR>
    <TR><TD>미확약</TD><TD>29,439</TD><TD>1.8</TD></TR></TABLE>
    """
    rows = irp.extract_rows(text)
    assert ["15일 확약", "26,458", "2.1"] in rows
    assert ["미확약", "29,439", "1.8"] in rows


# 마키나락스 증권발행실적보고서(20260514001096) 실측 — 청약·배정현황 표
MAKINA_ALLOC = """
<TABLE>
<TR><TD>구분</TD><TD>수량</TD><TD>비율</TD><TD>건수</TD><TD>수량</TD><TD>금액</TD><TD>비율</TD>
    <TD>건수</TD><TD>수량</TD><TD>금액</TD><TD>비율</TD></TR>
<TR><TD>우리사주조합</TD><TD>349,300</TD><TD>13.3</TD><TD>1</TD><TD>349,300</TD>
    <TD>5,239,500,000</TD><TD>0.0</TD><TD>1</TD><TD>349,300</TD>
    <TD>5,239,500,000</TD><TD>13.3</TD></TR>
<TR><TD>기관투자자</TD><TD>1,626,950</TD><TD>61.7</TD><TD>2,427</TD><TD>1,626,950</TD>
    <TD>24,404,250,000</TD><TD>0.1</TD><TD>2,427</TD><TD>1,626,950</TD>
    <TD>24,404,250,000</TD><TD>61.7</TD></TR>
<TR><TD>일반투자자</TD><TD>658,750</TD><TD>25.0</TD><TD>546,153</TD><TD>1,849,631,580</TD>
    <TD>27,744,473,700,000</TD><TD>99.9</TD><TD>545,850</TD><TD>658,750</TD>
    <TD>9,881,250,000</TD><TD>25.0</TD></TR>
<TR><TD>계</TD><TD>2,635,000</TD><TD>100.0</TD><TD>548,581</TD><TD>3,825,881,580</TD>
    <TD>27,773,727,700,000</TD><TD>100.0</TD><TD>548,578</TD><TD>2,635,000</TD>
    <TD>39,524,750,000</TD><TD>100.0</TD></TR>
</TABLE>
"""

# ESOP 우선배정 도입 후 사례: 최초배정 350k → 최종배정 200k로 감소 (150k 재배정)
# 이 케이스는 최初배定과 最終配定이 다를 때 올바른 인덱스를 선택하는지 검증
ESOP_CLAWBACK_ALLOC = """
<TABLE>
<TR><TD>구분</TD><TD>수량</TD><TD>비율</TD><TD>건수</TD><TD>수량</TD><TD>금액</TD><TD>비율</TD>
    <TD>건수</TD><TD>수량</TD><TD>금액</TD><TD>비율</TD></TR>
<TR><TD>우리사주조합</TD><TD>350,000</TD><TD>14.0</TD><TD>1</TD><TD>350,000</TD>
    <TD>5,250,000,000</TD><TD>0.1</TD><TD>1</TD><TD>200,000</TD>
    <TD>3,000,000,000</TD><TD>8.0</TD></TR>
<TR><TD>기관투자자</TD><TD>1,500,000</TD><TD>60.0</TD><TD>2,000</TD><TD>1,500,000</TD>
    <TD>22,500,000,000</TD><TD>50.0</TD><TD>2,300</TD><TD>1,800,000</TD>
    <TD>27,000,000,000</TD><TD>72.0</TD></TR>
<TR><TD>일반투자자</TD><TD>650,000</TD><TD>26.0</TD><TD>400,000</TD><TD>1,650,000</TD>
    <TD>24,750,000,000</TD><TD>49.9</TD><TD>388,000</TD><TD>700,000</TD>
    <TD>10,500,000,000</TD><TD>20.0</TD></TR>
<TR><TD>계</TD><TD>2,500,000</TD><TD>100.0</TD><TD>402,001</TD><TD>3,500,000</TD>
    <TD>52,500,000,000</TD><TD>100.0</TD><TD>390,301</TD><TD>2,700,000</TD>
    <TD>40,500,000,000</TD><TD>100.0</TD></TR>
</TABLE>
"""

# 정수형 비율을 포함한 fixture: 100% = "100" (소수점 없음)
# parse_qty("100") = 100이므로 위치 기반 추출이 실패하는 사례
# INST 행에만 "100"이 있으면, INST와 계는 둘 다 shift되지만
# RETAIL은 shift 안 되므로 합계가 맞지 않음 → None 반환하여 버그 감지
BARE_INTEGER_RATIO_ALLOC = """
<TABLE>
<TR><TD>구분</TD><TD>수량</TD><TD>비율</TD><TD>건수</TD><TD>수량</TD><TD>금액</TD><TD>비율</TD>
    <TD>건수</TD><TD>수량</TD><TD>금액</TD><TD>비율</TD></TR>
<TR><TD>우리사주조합</TD><TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD>
    <TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD></TR>
<TR><TD>기관투자자</TD><TD>1,500,000</TD><TD>100</TD><TD>2,000</TD><TD>1,500,000</TD>
    <TD>22,500,000,000</TD><TD>100</TD><TD>2,000</TD><TD>1,500,000</TD>
    <TD>22,500,000,000</TD><TD>100</TD></TR>
<TR><TD>일반투자자</TD><TD>500,000</TD><TD>33.3</TD><TD>100,000</TD><TD>500,000</TD>
    <TD>7,500,000,000</TD><TD>25.0</TD><TD>100,000</TD><TD>500,000</TD>
    <TD>7,500,000,000</TD><TD>33.3</TD></TR>
<TR><TD>계</TD><TD>2,000,000</TD><TD>100.0</TD><TD>102,000</TD><TD>2,000,000</TD>
    <TD>30,000,000,000</TD><TD>100.0</TD><TD>102,000</TD><TD>2,000,000</TD>
    <TD>30,000,000,000</TD><TD>100.0</TD></TR>
</TABLE>
"""


def test_parse_allocation_table_makinarocks():
    r = irp.parse_allocation_table(MAKINA_ALLOC)
    assert r["esop"] == 349_300
    assert r["inst"] == 1_626_950
    assert r["retail"] == 658_750       # 청약수량 1,849,631,580이 아닌 최종배정


def test_parse_allocation_inst_matches_lockup_total():
    """배정현황의 기관 수량 == 확약표의 '계'. 두 표가 독립이라 교차검증이 된다."""
    alloc = irp.parse_allocation_table(MAKINA_ALLOC)
    lock = irp.parse_lockup_table(MAKINA_TABLE)
    assert alloc["inst"] == lock["total"] == 1_626_950


def test_parse_allocation_no_esop():
    """우리사주 배정이 없는 딜(토모큐브)은 esop=0."""
    text = """
    <TABLE>
    <TR><TD>우리사주조합</TD><TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD>
        <TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD><TD>-</TD></TR>
    <TR><TD>기관투자자</TD><TD>1,500,000</TD><TD>75.0</TD><TD>2,377</TD><TD>1,500,000</TD>
        <TD>24,000,000,000</TD><TD>13.1</TD><TD>2,377</TD><TD>1,500,000</TD>
        <TD>24,000,000,000</TD><TD>75.0</TD></TR>
    </TABLE>
    """
    r = irp.parse_allocation_table(text)
    assert r["esop"] == 0
    assert r["inst"] == 1_500_000


def test_parse_allocation_missing_inst_returns_none():
    """기관투자자 행이 없으면 불완전한 배정현황 → None 반환."""
    text = """
    <TABLE>
    <TR><TD>우리사주조합</TD><TD>349,300</TD><TD>13.3</TD><TD>1</TD><TD>349,300</TD>
        <TD>5,239,500,000</TD><TD>0.0</TD><TD>1</TD><TD>349,300</TD>
        <TD>5,239,500,000</TD><TD>13.3</TD></TR>
    <TR><TD>일반투자자</TD><TD>658,750</TD><TD>25.0</TD><TD>546,153</TD><TD>1,849,631,580</TD>
        <TD>27,744,473,700,000</TD><TD>99.9</TD><TD>545,850</TD><TD>658,750</TD>
        <TD>9,881,250,000</TD><TD>25.0</TD></TR>
    </TABLE>
    """
    r = irp.parse_allocation_table(text)
    assert r is None


def test_parse_allocation_esop_clawback_picks_final_not_initial():
    """최初배定과 最終配定이 다를 때 최종 값을 선택하는지 검증.

    이 테스트는 qtys[1]이 정확한지 실증적으로 검증한다.
    만약 qtys[-1] (최초배정)을 선택하면 ESOP이 350,000으로 틀린다.
    """
    r = irp.parse_allocation_table(ESOP_CLAWBACK_ALLOC)
    assert r["esop"] == 200_000, "최終배定 선택"
    assert r["inst"] == 1_800_000, "최終배定 선택"
    assert r["retail"] == 700_000, "최終배定 선택"
    # 검증: esop + inst + retail == 계
    assert r["esop"] + r["inst"] + r["retail"] == 2_700_000


def test_parse_allocation_sum_matches_total_row():
    """배정현황 3그룹의 합이 계 행과 일치하는지 검증.

    마키나락스: 349,300 + 1,626,950 + 658,750 = 2,635,000 (계)
    ESOP 우선배정 케이스: 200,000 + 1,800,000 + 700,000 = 2,700,000 (계)
    """
    r1 = irp.parse_allocation_table(MAKINA_ALLOC)
    assert r1["esop"] + r1["inst"] + r1["retail"] == 2_635_000

    r2 = irp.parse_allocation_table(ESOP_CLAWBACK_ALLOC)
    assert r2["esop"] + r2["inst"] + r2["retail"] == 2_700_000


def test_parse_allocation_bare_integer_ratio_fails_gracefully():
    """정수형 비율 ('100')을 포함한 행에서 위치 기반 추출이 실패하면 None 반환.

    This tests Issue #3: 위치 기반 추출의 취약점.
    "100" (bare integer)가 비율 위치에 있으면 parse_qty()가 100을 수량으로 인식,
    일부 행의 인덱스가 shift되어 잘못된 배정수량을 반환할 수 있다.

    이 테스트는 합계 검증으로 mismatch를 감지하고 None 반환하는지 확인한다.
    INST 행에만 "100"이 있으므로 INST는 shift되지만 RETAIL은 정상.
    따라서 esop(0) + inst(shifted) + retail(500k) ≠ 계(2M)가 되어
    mismatch 검출 → None 반환.
    """
    r = irp.parse_allocation_table(BARE_INTEGER_RATIO_ALLOC)
    # 합계 검증이 실패하면 None을 반환해야 함 (부분 채워진 dict 금지)
    # 이는 위치 기반 추출 오류를 감지하기 위한 safety valve 역할
    assert r is None, "bare-integer ratio shift로 인한 mismatch를 감지하고 None 반환해야 함"


# ============================================================================
# Task 4b — ACODE 기반 파서. 실문서에서 뜬 fixture로만 검증한다 (합성 <TD> 금지).
#
# Task 2~4의 fixture는 전부 손으로 쓴 <TD> 마크업이었고, 실문서는 <TE>+ACODE를
# 쓴다는 사실을 41개 테스트 전부가 놓쳤다 — 그 결과 955사 재수집에서 ok=0이 나왔다.
# 이 섹션의 테스트는 tools/dump_fixture.py로 실문서에서 잘라낸 표 조각만 사용한다.
# ============================================================================


def test_extract_rows_with_acode_reads_te_cells_and_acode():
    """<TE ACODE=...> 셀을 (ACODE, 값) 쌍으로 돌려준다. ACODE 없으면 None."""
    text = """
    <TABLE><TR>
    <TE ACODE="DST_CD">우리사주조합</TE>
    <TE ACODE="DV_ST_CNT">349,300</TE>
    <TD>비고없음</TD>
    </TR></TABLE>
    """
    rows = irp.extract_rows_with_acode(text)
    assert rows == [[("DST_CD", "우리사주조합"), ("DV_ST_CNT", "349,300"), (None, "비고없음")]]


def test_extract_rows_still_returns_plain_cell_values():
    """기존 extract_rows() 시그니처는 유지 — <TE>도 포함해서 값만 반환."""
    text = '<TABLE><TR><TE ACODE="DST_CD">기관투자자</TE><TE ACODE="DV_ST_CNT">1,626,950</TE></TR></TABLE>'
    rows = irp.extract_rows(text)
    assert rows == [["기관투자자", "1,626,950"]]


def test_parse_allocation_table_makinarocks_real_document():
    """실문서(마키나락스 20260514001096) 배정현황 표 조각.

    DST_CD로 라벨을, DV_ST_CNT로 최종배정수량을 읽는다 — 위치 추측이 아니다.
    """
    text = _load_fixture("impl_report_20260514001096_alloc.xml")
    r = irp.parse_allocation_table(text)
    assert r == {"esop": 349_300, "inst": 1_626_950, "retail": 658_750}


def test_parse_lockup_table_acode_makinarocks_real_document():
    """실문서(마키나락스 20260514001096) 확약표 조각 — ACODE 경로 자체를 검증.

    코드리뷰 지적사항: 공개 함수 parse_lockup_table()로 검증하면 이 fixture는
    "합계가 각 행의 최댓값"이라는 우연 때문에 positional fallback(_row_total_qty의
    max() 휴리스틱)도 똑같은 정답을 낸다. 그래서 LOCKUP_TOTAL_ACODES를 통째로
    비워 ACODE 경로를 완전히 죽여도 공개 함수 테스트는 폴백을 타고 바이트 단위로
    동일하게 통과해버려 회귀를 잡지 못했다(리뷰어가 실측 확인, task-4b-report.md
    "Step 6 코드리뷰 대응" 참고). _parse_lockup_table_acode()를 직접 호출해
    ACODE 경로만 떼어내 검증한다.

    합계 열 ACODE는 행마다 다르다 (기간행=TOT_CNT, 미확약=NTOT_CNT, 계=TTOT_CNT).
    """
    text = _load_fixture("impl_report_20260514001096_lockup.xml")
    r = irp._parse_lockup_table_acode(text)
    assert r is not None, "ACODE 경로가 값을 만들어내지 못했다"
    assert r["total"] == 1_626_950
    assert r["none"] == 29_439
    assert r["locked"] == 1_597_511
    assert r["6m"] == 842_820
    assert r["3m"] == 520_076
    assert r["1m"] == 151_465
    assert r["15d"] == 83_150
    # 공개 API도 ACODE 경로 결과를 그대로 반환해야 한다 (폴백으로 새지 않는지 확인)
    assert irp.parse_lockup_table(text) == r


def test_parse_lockup_table_acode_legacy_2017_2021_scheme():
    """실문서(대원 20171128000032, 2017년) 확약표 조각 — 구형 ACODE 체계, ACODE 경로 자체를 검증.

    위 마키나락스 테스트와 같은 이유로 _parse_lockup_table_acode()를 직접 호출한다.

    Step 1 조사 결과: 2017~2021 문서는 기관투자자 카테고리 세분화가 없어
    확약 우선배정 이전의 단순 구조다. 라벨 ACODE는 확약기간 행에만
    (ASS_PRD) 있고, 미확약/합계 행은 라벨에 ACODE가 아예 없다(<TD>).
    합계 열 ACODE도 행마다 다르다: 확약기간행=ASS_CNT, 미확약=NASS_CNT,
    합계=SUM_NASS_CNT. 원문을 눈으로 읽은 값:
      15일 10,000 / 1개월 - / 3개월 - / 미확약 1,390,000 / 합계 1,400,000
    """
    text = _load_fixture("impl_report_20171128000032_lockup.xml")
    r = irp._parse_lockup_table_acode(text)
    assert r is not None, "ACODE 경로가 값을 만들어내지 못했다"
    assert r["total"] == 1_400_000
    assert r["none"] == 1_390_000
    assert r["15d"] == 10_000
    assert r["1m"] == 0
    assert r["3m"] == 0
    assert r["6m"] == 0
    assert r["locked"] == 10_000
    # 공개 API도 ACODE 경로 결과를 그대로 반환해야 한다 (폴백으로 새지 않는지 확인)
    assert irp.parse_lockup_table(text) == r


def test_parse_allocation_dv_st_cnt_differs_from_both_initial_and_subscription():
    """DV_ST_CNT(최종배정)가 FST_DV_CNT(최초배정)·SB_ST_CNT(청약)와 모두 다른 실문서 pin.

    브리프가 제시한 마키나락스 예시는 사실 FST_DV_CNT == DV_ST_CNT라 최초/최종배정
    구분을 pin하지 못한다(청약과의 구분만 됨). 실문서에서 세 값이 전부 다른 행을
    찾아 대체했다: LG에너지솔루션(20220121000496) 일반투자자 행 —
      FST_DV_CNT 10,625,000 / SB_ST_CNT 760,710,960 / DV_ST_CNT 10,970,482
    (청약 대비 배정 축소 + 최초배정 대비 최종배정 증가가 동시에 일어난 사례)
    """
    text = _load_fixture("impl_report_20220121000496_alloc.xml")
    r = irp.parse_allocation_table(text)
    assert r == {"esop": 8_154_518, "inst": 23_375_000, "retail": 10_970_482}
    assert r["esop"] + r["inst"] + r["retail"] == 42_500_000  # 계 행 DV_ST_CNT_TOT


def test_parse_allocation_table_falls_back_to_positional_when_no_acode():
    """ACODE가 전혀 없는 문서(합성 <TD> fixture)는 기존 위치 기반 경로로 폴백한다."""
    r = irp.parse_allocation_table(MAKINA_ALLOC)
    assert r == {"esop": 349_300, "inst": 1_626_950, "retail": 658_750}


def test_parse_lockup_table_falls_back_to_positional_when_no_acode():
    """ACODE가 전혀 없는 문서(합성 <TD> fixture)는 기존 max() 경로로 폴백한다."""
    r = irp.parse_lockup_table(MAKINA_TABLE)
    assert r["total"] == 1_626_950
    assert r["none"] == 29_439
