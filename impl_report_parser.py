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


# 청약·배정현황 표 행 라벨 → 표준 키
ALLOC_LABELS = {"우리사주조합": "esop", "기관투자자": "inst", "일반투자자": "retail"}


def _final_alloc_qty(cells: list[str]) -> int:
    """최종 배정수량 = 뒤에서 두 번째 수량 셀.

    「최종 배정 현황」 구획은 (건수, 수량, 금액, 비율) 순서로 끝난다.
    비율은 소수점이 있어 parse_qty가 걸러내므로, 뒤에서부터 수량형 셀을
    모으면 [금액, 수량, 건수, ...] 순서가 되고 인덱스 1이 배정수량이다.
    전부 '-'인 행(우리사주 미배정 등)은 0.

    마키나락스 일반투자자 행으로 검증:
      [... '545,850', '658,750', '9,881,250,000', '25.0']
      → qtys = [9881250000, 658750, 545850, ...] → qtys[1] = 658,750 ✓
      (qtys[2]는 청약건수 545,850을 집는다 — 인덱스를 옮기지 말 것)
    """
    qtys = [q for q in (parse_qty(c) for c in reversed(cells[1:])) if q is not None]
    if len(qtys) >= 2:
        return qtys[1]
    return qtys[-1] if qtys else 0


def parse_allocation_table(text: str) -> dict | None:
    """「청약 및 배정현황」 표에서 그룹별 최종 배정수량을 파싱.

    반환: {"esop": int, "inst": int, "retail": int} 또는 None
    - inst 없으면 None (필수 키)
    - esop/retail 없으면 0 (선택 키)
    - 내부 검증: esop + inst + retail == 계 행의 배정수량. 불일치 시 None 반환.
      이는 위치 기반 추출의 index shift 버그를 감지하기 위함.
    """
    out = {}
    total_from_계 = None

    for cells in extract_rows(text):
        if len(cells) < 2:
            continue
        label = WS_RE.sub("", cells[0])
        key = ALLOC_LABELS.get(label)
        if key is None:
            # 계 행에서 최종 배정 수량을 저장
            if label == "계":
                total_from_계 = _final_alloc_qty(cells)
            continue
        out[key] = _final_alloc_qty(cells)

    if "inst" not in out:
        return None
    out.setdefault("esop", 0)
    out.setdefault("retail", 0)

    # 내부 검증: 세 그룹의 합이 계 행과 일치하는지 확인
    if total_from_계 is not None:
        computed_total = out["esop"] + out["inst"] + out["retail"]
        if computed_total != total_from_계:
            # 합계 불일치 = 위치 기반 추출 오류 가능성 높음 → None 반환
            return None

    return out
