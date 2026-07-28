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
