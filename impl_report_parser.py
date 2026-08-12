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
# DART 데이터 셀은 <TE>다 (<TD>는 헤더/장식용). 셋 다 읽는다.
CELL_RE = re.compile(r"<T[DHE]\b([^>]*)>(.*?)</T[DHE]>", re.S | re.I)
ACODE_RE = re.compile(r'ACODE\s*=\s*"([^"]+)"', re.I)
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
    """<TR> 안의 <TD>/<TH>/<TE> 셀 값을 행 단위로. (기존 시그니처 유지 — fallback 경로가 의존)"""
    return [[v for _, v in row] for row in extract_rows_with_acode(text)]


def extract_rows_with_acode(text: str) -> list[list[tuple[str | None, str]]]:
    """<TR> 안의 셀을 (ACODE, 값) 쌍으로. ACODE 없으면 None.

    DART 문서는 데이터 셀에 <TE>를 쓰고 각 셀에 ACODE로 열의 의미를 박아둔다.
    위치로 열을 추측하지 않고 이 값을 직접 쓰는 것이 훨씬 견고하다.
    """
    rows = []
    for tr in TR_RE.findall(text):
        cells = []
        for attrs, raw in CELL_RE.findall(tr):
            m = ACODE_RE.search(attrs)
            cells.append((m.group(1) if m else None, normalize_cell(raw)))
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
# ACODE 경로에서는 "확약"이 붙지 않은 맨 라벨("15일", "1개월"...)도 실문서에서 쓰인다
# (2017~2021년 문서, 예: 대원 20171128000032). 둘 다 등록해 둔다.
LOCKUP_LABELS = {
    "15일확약": "15d", "2주일확약": "15d", "2주확약": "15d",
    "15일": "15d", "2주일": "15d", "2주": "15d",
    "1개월확약": "1m", "3개월확약": "3m", "6개월확약": "6m",
    "1개월": "1m", "3개월": "3m", "6개월": "6m",
    "미확약": "none", "계": "total", "합계": "total",
}

# 확약표 "합계 열" ACODE — Step 1 실측 조사 결과 (rcept 다수 실문서 대조).
#
# 기대와 달리 ACODE는 시기가 아니라 "행의 역할"에 따라 갈린다. 문서 하나 안에서도
# 확약기간 행 / 미확약 행 / 계 행이 서로 다른 ACODE를 쓴다:
#
#   행 역할        기관 카테고리 세분화 있음(2016,2022~2026)   세분화 없음(2017~2021)
#   확약기간 행     TOT_CNT                                   ASS_CNT
#   미확약 행       NTOT_CNT                                  NASS_CNT
#   계(합계) 행     TTOT_CNT                                  SUM_NASS_CNT
#
# 브리프가 제시한 "TOT_CNT가 전 연도 합계 열"이라는 가정은 틀렸다 — 브리프의 예시인
# 마키나락스(2026, 20260514001096) 원문에서도 미확약 행은 NTOT_CNT, 계 행은
# TTOT_CNT를 쓴다(TOT_CNT가 아니다). 실측: 미확약 NTOT_CNT=29,439, 계 TTOT_CNT=1,626,950
# — 브리프 본문의 "실측 검증" 수치와 일치.
#
# 한 행에는 이 중 정확히 하나만 나타나므로, 행마다 이 집합에서 매칭되는 것을 찾으면 된다.
LOCKUP_TOTAL_ACODES = ("TOT_CNT", "NTOT_CNT", "TTOT_CNT", "ASS_CNT", "NASS_CNT", "SUM_NASS_CNT")

# 라벨 ACODE. 확약기간 행에만 있다 — 미확약/계 행은 라벨 셀에 ACODE가 없다(<TD>).
_LOCKUP_LABEL_ACODE = "ASS_PRD"


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


def _parse_lockup_table_acode(text: str) -> dict | None:
    """ACODE 기반 확약표 파싱. ACODE 체계가 아예 없는 문서면 None (폴백 신호)."""
    out = {}
    saw_acode = False
    for cells in extract_rows_with_acode(text):
        if len(cells) < 2:
            continue
        acodes_here = {a for a, _ in cells if a}
        if not (acodes_here & ({_LOCKUP_LABEL_ACODE} | set(LOCKUP_TOTAL_ACODES))):
            continue
        saw_acode = True
        # 라벨 = 첫 셀 값 (ASS_PRD 있으면 그 값, 없어도 <TD> 첫 셀이 라벨이다)
        label = WS_RE.sub("", cells[0][1])
        key = LOCKUP_LABELS.get(label)
        if key is None:
            continue
        qty = None
        for a, v in cells:
            if a in LOCKUP_TOTAL_ACODES:
                qty = parse_qty(v)
                break
        out[key] = qty if qty is not None else 0

    if not saw_acode:
        return None
    if "total" not in out or "none" not in out:
        return None
    for k in ("15d", "1m", "3m", "6m"):
        out.setdefault(k, 0)
    out["locked"] = out["total"] - out["none"]
    return out


def _parse_lockup_table_positional(text: str) -> dict | None:
    """위치(max()) 기반 확약표 파싱 — ACODE가 없는 문서용 fallback."""
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


def parse_lockup_table(text: str) -> dict | None:
    """「기관투자자 의무보유확약기간별 배정현황」 표를 파싱.

    ACODE(열 식별자)가 있으면 그 값을 직접 읽는다. 없으면(합성 <TD> fixture 등)
    기존 위치 기반(max()) 경로로 폴백한다.

    반환: {"total","none","15d","1m","3m","6m","locked"} / 표 없으면 None
    """
    out = _parse_lockup_table_acode(text)
    if out is not None:
        return out
    return _parse_lockup_table_positional(text)


# 청약·배정현황 표 행 라벨 → 표준 키
ALLOC_LABELS = {"우리사주조합": "esop", "기관투자자": "inst", "일반투자자": "retail"}

# 배정현황 표 ACODE (전 연도 2016~2026 동일 — 실측: 마키나락스 2026, 대원 2017 등).
_ALLOC_LABEL_ACODE = "DST_CD"
_ALLOC_QTY_ACODE = "DV_ST_CNT"   # 최종 배정 수량. FST_DV_CNT(최초배정)·SB_ST_CNT(청약)와 혼동 금지.


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


def _parse_allocation_table_acode(text: str) -> dict | None:
    """ACODE 기반 배정현황 파싱. ACODE 체계가 아예 없는 문서면 None (폴백 신호).

    DST_CD로 행을 식별하고 DV_ST_CNT를 직접 읽으므로 위치를 추측하지 않는다.
    계 행 체크섬은 여기서 불필요하다 — 열을 정확히 지목하기 때문에 자기검증할
    이유가 없고, 실문서의 계 행 비율이 정수 "100"이라 오히려 오탐을 냈다
    (positional 경로에서만 그 체크섬이 남아 있다).

    반환 3종을 구분한다:
      None : ACODE 체계가 아예 없는 문서 — positional 폴백 신호
      {}   : ACODE 문서인데 필수 수량을 못 읽음 — 폴백 금지, 상위에서 partial 처리
      dict : 정상 파싱
    """
    out = {}
    saw_acode = False
    for cells in extract_rows_with_acode(text):
        if len(cells) < 2:
            continue
        acode_map = {a: v for a, v in cells if a}
        if _ALLOC_LABEL_ACODE not in acode_map:
            continue
        saw_acode = True
        label = WS_RE.sub("", acode_map[_ALLOC_LABEL_ACODE])
        key = ALLOC_LABELS.get(label)
        if key is None:
            continue
        if _ALLOC_QTY_ACODE not in acode_map:
            # 라벨은 인식했는데 수량 열 자체가 없다. 0으로 단정하면 기관배정
            # 0주가 조용히 B와 확약률에 흘러 들어간다 — 모른다고 기록한다.
            out[key] = None
            continue
        qty = parse_qty(acode_map[_ALLOC_QTY_ACODE])
        # 셀이 존재하는데 '-'/빈칸이면 진짜 미배정이다 (우리사주 무배정 등) → 0.
        out[key] = qty if qty is not None else 0

    if not saw_acode:
        return None
    # 라벨은 인식했는데 수량 열이 없는 행이 있으면 표 전체를 신뢰하지 않는다.
    # 여기서만 폴백을 막는다 — positional 경로는 열 위치를 추측하므로 부분 ACODE
    # 문서에서 오답을 확신할 수 있다(원장 #14). 그 밖의 경우는 종전과 동일하게
    # 동작시킨다: 라벨 자체를 못 찾은 것(아래 "inst" not in out)은 라벨 변형일
    # 수 있고, 그때의 폴백은 기존에 쓰이던 정상 경로다.
    if any(v is None for v in out.values()):
        return {}
    if "inst" not in out:
        return None
    out.setdefault("esop", 0)
    out.setdefault("retail", 0)
    return out


def _parse_allocation_table_positional(text: str) -> dict | None:
    """위치 기반 배정현황 파싱 — ACODE가 없는 문서용 fallback.

    반환: {"esop": int, "inst": int, "retail": int} 또는 None
    - inst 없으면 None (필수 키)
    - esop/retail 없으면 0 (선택 키)
    - 내부 검증: esop + inst + retail == 계 행의 배정수량. 불일치 시 None 반환.
      이는 위치 기반 추출의 index shift 버그를 감지하기 위함. ACODE 경로는
      열을 정확히 지목하므로 이 체크섬이 없다 — positional 경로에만 남긴다.
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


def parse_allocation_table(text: str) -> dict | None:
    """「청약 및 배정현황」 표에서 그룹별 최종 배정수량을 파싱.

    ACODE(DST_CD/DV_ST_CNT)가 있으면 그 값을 직접 읽는다. 없으면(합성 <TD>
    fixture 등) 기존 위치 기반 경로(+계 행 체크섬)로 폴백한다.

    반환: {"esop": int, "inst": int, "retail": int}
          / 표 자체가 없으면 None
          / ACODE 문서인데 수량을 못 읽었으면 {} (falsy — 호출부에서 partial)
    """
    out = _parse_allocation_table_acode(text)
    if out is not None:
        return out
    return _parse_allocation_table_positional(text)
