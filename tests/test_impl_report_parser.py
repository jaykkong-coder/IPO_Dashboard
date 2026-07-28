import impl_report_parser as irp


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
