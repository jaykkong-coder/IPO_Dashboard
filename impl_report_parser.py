"""DART 증권발행실적보고서 순수 파싱 모듈 (네트워크 없음).

「기관투자자 의무보유확약기간별 배정현황」과 「청약 및 배정현황」 표에서
확약물량·우리사주·기관배정을 추출한다.

인코딩 주의: 2022년 이전 문서는 EUC-KR(cp949)이다. utf-8 우선 시도 후 폴백한다.
"""
import re

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
DIGIT_GAP_RE = re.compile(r"(?<=\d)\s+(?=\d)")   # DART가 숫자 중간에 개행을 넣는 경우
TR_RE = re.compile(r"<TR\b[^>]*>(.*?)</TR>", re.S | re.I)
CELL_RE = re.compile(r"<T[DH]\b[^>]*>(.*?)</T[DH]>", re.S | re.I)
QTY_RE = re.compile(r"^-?[\d,]+$")


def decode_document(raw: bytes) -> str:
    """DART 원문 bytes를 문자열로. utf-8 → cp949 순차 시도."""
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp949", errors="ignore")


def normalize_cell(raw: str) -> str:
    txt = TAG_RE.sub("", raw)
    txt = DIGIT_GAP_RE.sub("", txt)
    return WS_RE.sub(" ", txt).strip()


def extract_rows(text: str) -> list[list[str]]:
    """<TR>/<TD> 표를 셀 리스트의 리스트로."""
    rows = []
    for tr in TR_RE.findall(text):
        cells = [normalize_cell(c) for c in CELL_RE.findall(tr)]
        if cells:
            rows.append(cells)
    return rows


def parse_qty(cell: str) -> int | None:
    """수량 셀을 정수로. '-'/빈칸/비중(소수점)은 None."""
    s = (cell or "").strip()
    if not s or s == "-":
        return None
    if not QTY_RE.match(s):
        return None
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


# 확약기간 행 라벨 → 표준 키. '2주일'과 '15일'은 같은 범주다.
LOCKUP_LABELS = {
    "15일확약": "15d", "2주일확약": "15d", "2주확약": "15d",
    "1개월확약": "1m", "3개월확약": "3m", "6개월확약": "6m",
    "미확약": "none", "계": "total", "합계": "total",
}


def _row_total_qty(cells: list[str]) -> int:
    """행에서 가장 큰 수량 셀을 합계로 반환. 전부 '-'면 0.

    합계 열을 지정 위치가 아닌 최댓값으로 선택하는 이유:
    - DART 파일별로 투자자유형 열 개수가 다름 (열 위치 불안정)
    - 비중이 정수("100") 또는 소수("100.0")로 표기되어 parse_qty()로 구분 불가
    - 수학적으로 합계(총합)는 컴포넌트 중 가장 큼 (합계 ≥ 모든 컴포넌트)
    """
    quantities = []
    for c in cells[1:]:
        q = parse_qty(c)
        if q is not None:
            quantities.append(q)
    return max(quantities) if quantities else 0


def parse_lockup_table(text: str) -> dict | None:
    """「기관투자자 의무보유확약기간별 배정현황」 표를 파싱.

    반환: {"total","none","15d","1m","3m","6m","locked"} / 표 없으면 None
    """
    out = {}
    for cells in extract_rows(text):
        if len(cells) < 2:
            continue
        label = WS_RE.sub("", cells[0])
        key = LOCKUP_LABELS.get(label)
        if key is None:
            continue
        out[key] = _row_total_qty(cells)

    if "total" not in out or "none" not in out:
        return None
    for k in ("15d", "1m", "3m", "6m"):
        out.setdefault(k, 0)
    out["locked"] = out["total"] - out["none"]
    return out
