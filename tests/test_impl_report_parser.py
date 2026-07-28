import impl_report_parser as irp


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
