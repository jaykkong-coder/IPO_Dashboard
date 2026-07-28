# 상장일 물량구조 재정의 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 의무보유확약비율과 유통가능주식수비율을 하나의 물량 항등식(`보호예수 + 기관확약 + 우리사주 + 실유통 = 상장예정주식수`)으로 통합하고, DART 증권발행실적보고서를 정본으로 삼아 955사 전수 재수집한다.

**Architecture:** 파싱(순수 함수)과 수집(네트워크)을 파일 단위로 분리해 테스트 가능성을 확보한다. 확약·우리사주·기관배정은 DART 증권발행실적보고서에서, 보호예수는 기존 `verify_float_extractor.py`(wrong-confident 0건 검증됨)로 추출한다. 두 소스를 항등식으로 병합하며 4중 게이트를 통과한 건만 자동 승인한다.

**Tech Stack:** Python 3, sqlite3, requests, pytest. 기존 모듈 `perf_common`(DB/유니버스), `pipeline.DART_API_KEY`, `verify_float_extractor`(A 추출) 재사용.

**설계 문서:** `docs/superpowers/specs/2026-07-28-share-structure-redefinition-design.md`

## Global Constraints

- 기존 `ipo_companies` 컬럼(`의무보유확약비율`, `유통가능주식수비율`)은 **수정 금지**. 신규 테이블에만 적재한다.
- DART API 키는 `from pipeline import DART_API_KEY` 로 가져온다. 하드코딩 금지.
- DART 응답 `status` 처리: `"000"` 성공 / `"013"` 정상(자료 없음) / `{"020","800"}` 한도초과 → 즉시 `RuntimeError` / 그 외 → `[WARN]` 출력 후 skip. `collect_quarterly.py:87-96` 패턴을 그대로 따른다.
- 네트워크 재시도는 `collect_quarterly._fetch_with_retry` 와 동일한 5/30/120초 백오프를 쓴다.
- DART 문서 디코딩은 **`utf-8` → `cp949` 순차 시도**. 구형 문서(2022년 이전)는 EUC-KR이다.
- 추정값으로 빈칸을 채우지 않는다. 확정 못 한 건은 `verdict='failed'` 로 남긴다.
- 네트워크가 필요한 테스트는 `@pytest.mark.network` 를 붙인다 (`pytest.ini` 에 마커 등록되어 있음).
- 작업 브랜치: `feat/share-structure-redefinition`
- 커밋 메시지는 한국어 본문 + Conventional Commits 접두어(`feat:`/`fix:`/`test:`/`docs:`).

---

## File Structure

| 파일 | 책임 |
|---|---|
| `perf_common.py` (수정) | `share_structure`, `impl_reports` DDL 추가 |
| `impl_report_parser.py` (신규) | 증권발행실적보고서 **순수 파싱** — 네트워크 없음, 문자열 → dict |
| `collect_impl_reports.py` (신규) | DART 조회 드라이버 — 문서 탐색·다운로드·`impl_reports` 적재 |
| `extract_float_all.py` (신규) | A(보호예수) 추출 드라이버 — `verify_float_extractor` 전기간 적용 |
| `build_share_structure.py` (신규) | 항등식 병합 + 4중 검증 → `share_structure` 적재 |
| `tests/test_impl_report_parser.py` (신규) | 파서 단위테스트 (고정 샘플) |
| `tests/test_build_share_structure.py` (신규) | 검증 게이트 단위테스트 |

---

### Task 1: 스키마 정의

**Files:**
- Modify: `perf_common.py:46-61` (DDL 리스트)
- Test: `tests/test_perf_common.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: 없음
- Produces: `perf_common.DDL` 에 `impl_reports`, `share_structure` 테이블 추가. `pc.ensure_tables(con)` 호출 시 생성됨.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_perf_common.py` 끝에 추가:

```python
def test_ensure_tables_creates_share_structure(tmp_path, monkeypatch):
    """share_structure / impl_reports 테이블이 ensure_tables로 생성된다."""
    import sqlite3
    import perf_common as pc

    con = sqlite3.connect(":memory:")
    pc.ensure_tables(con)
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "share_structure" in names
    assert "impl_reports" in names

    cols = {r[1] for r in con.execute("PRAGMA table_info(share_structure)")}
    for c in ("corp_code", "total_shares", "lockup_existing", "lockup_inst",
              "esop", "free_float", "free_float_pct", "inst_alloc",
              "lockup_inst_pct", "identity_gap", "verdict"):
        assert c in cols, f"missing column {c}"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_perf_common.py::test_ensure_tables_creates_share_structure -v`
Expected: FAIL — `AssertionError: 'share_structure' not in names`

- [ ] **Step 3: DDL 추가**

`perf_common.py` 의 `DDL` 리스트 마지막 항목 뒤에 두 개를 추가한다:

```python
    """CREATE TABLE IF NOT EXISTS impl_reports(
        corp_code TEXT PRIMARY KEY,
        rcept_no TEXT,
        report_nm TEXT,
        inst_alloc INTEGER,
        esop INTEGER,
        retail_alloc INTEGER,
        lockup_none INTEGER,
        lockup_15d INTEGER,
        lockup_1m INTEGER,
        lockup_3m INTEGER,
        lockup_6m INTEGER,
        parse_status TEXT,
        fetched_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS share_structure(
        corp_code TEXT PRIMARY KEY,
        listing_date TEXT,
        total_shares INTEGER,
        lockup_existing INTEGER,
        lockup_inst INTEGER,
        esop INTEGER,
        free_float INTEGER,
        free_float_pct REAL,
        inst_alloc INTEGER,
        lockup_inst_pct REAL,
        lockup_15d INTEGER,
        lockup_1m INTEGER,
        lockup_3m INTEGER,
        lockup_6m INTEGER,
        identity_gap REAL,
        verdict TEXT,
        src_impl_rcept TEXT,
        src_prosp_rcept TEXT,
        evidence TEXT,
        updated_at TEXT)""",
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_perf_common.py -v`
Expected: PASS (기존 테스트 포함 전부)

- [ ] **Step 5: 커밋**

```bash
git add perf_common.py tests/test_perf_common.py
git commit -m "feat: share_structure·impl_reports 스키마 추가"
```

---

### Task 2: 문서 디코딩 + 표 추출 유틸

**Files:**
- Create: `impl_report_parser.py`
- Test: `tests/test_impl_report_parser.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `decode_document(raw: bytes) -> str` — utf-8→cp949 순차 디코드
  - `extract_rows(text: str) -> list[list[str]]` — `<TR>/<TD>` 파싱, 셀은 태그 제거·공백 정규화됨
  - `parse_qty(cell: str) -> int | None` — `"1,626,950"`→`1626950`, `"-"`/`""`→`None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_impl_report_parser.py` 생성:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_impl_report_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'impl_report_parser'`

- [ ] **Step 3: 구현**

`impl_report_parser.py` 생성:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_impl_report_parser.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add impl_report_parser.py tests/test_impl_report_parser.py
git commit -m "feat: 증권발행실적보고서 디코딩·표추출 유틸"
```

---

### Task 3: 확약표 파서

확약표는 `확약기간 × 투자자유형` 격자이고 **맨 오른쪽이 합계 열**이다. 투자자유형 열 개수가
시기별로 다르므로 열 위치를 고정하지 말고 "행의 마지막 수량 셀"을 합계로 잡는다.
행 라벨은 시기별로 `15일 확약` / `2주일 확약` 두 표기가 모두 쓰이며 같은 범주다.

**Files:**
- Modify: `impl_report_parser.py`
- Test: `tests/test_impl_report_parser.py`

**Interfaces:**
- Consumes: `extract_rows`, `parse_qty` (Task 2)
- Produces: `parse_lockup_table(text: str) -> dict | None`
  반환 키: `{"total": int, "none": int, "15d": int, "1m": int, "3m": int, "6m": int, "locked": int}`
  `locked = total - none`. 표가 없으면 `None`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_impl_report_parser.py` 에 추가. 값은 DART 원문 실측치다.

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_impl_report_parser.py -k lockup -v`
Expected: FAIL — `AttributeError: module 'impl_report_parser' has no attribute 'parse_lockup_table'`

- [ ] **Step 3: 구현**

`impl_report_parser.py` 에 추가:

```python
# 확약기간 행 라벨 → 표준 키. '2주일'과 '15일'은 같은 범주다.
LOCKUP_LABELS = {
    "15일확약": "15d", "2주일확약": "15d", "2주확약": "15d",
    "1개월확약": "1m", "3개월확약": "3m", "6개월확약": "6m",
    "미확약": "none", "계": "total", "합계": "total",
}


def _row_total_qty(cells: list[str]) -> int:
    """행의 마지막 수량 셀(=합계 열)을 반환. 전부 '-'면 0.

    합계 열은 항상 맨 오른쪽이지만 그 뒤에 비중 셀이 따라붙는다.
    뒤에서부터 훑어 처음 만나는 수량형 셀을 채택한다.
    """
    for c in reversed(cells[1:]):
        q = parse_qty(c)
        if q is not None:
            return q
    return 0


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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_impl_report_parser.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 확약 내부 정합성 테스트 추가**

`계 = 15d + 1m + 3m + 6m + 미확약` 이 성립해야 한다. 이 검증을 파서 사용자가 쓸 수 있게 노출한다.

```python
def test_lockup_components_sum_to_total():
    """확약기간별 합 + 미확약 = 계. 열 선택이 틀리면 여기서 깨진다."""
    for table in (MAKINA_TABLE, TOMO_TABLE):
        r = irp.parse_lockup_table(table)
        parts = r["15d"] + r["1m"] + r["3m"] + r["6m"] + r["none"]
        assert parts == r["total"], f"{parts} != {r['total']}"
```

Run: `python3 -m pytest tests/test_impl_report_parser.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: 커밋**

```bash
git add impl_report_parser.py tests/test_impl_report_parser.py
git commit -m "feat: 의무보유확약기간별 배정현황 파서 (합계열 자동탐색)"
```

---

### Task 4: 청약·배정현황 파서

「3. 청약 및 배정현황」 표에서 우리사주조합·기관투자자의 **최종 배정수량**을 뽑는다.
이 표는 `최초 배정 / 청약 현황 / 최종 배정 현황` 세 구획이 한 행에 이어 붙어 있어
행 안에 수량이 여러 번 등장한다. 최종 배정수량은 **뒤에서 세 번째 수량 셀**이다
(끝이 `수량, 금액, 비율` 순서이므로).

이 위치 가정은 Task 3의 확약표 `계`(=기관 총배정)와 교차검증해 안전성을 확보한다.

**Files:**
- Modify: `impl_report_parser.py`
- Test: `tests/test_impl_report_parser.py`

**Interfaces:**
- Consumes: `extract_rows`, `parse_qty` (Task 2)
- Produces: `parse_allocation_table(text: str) -> dict | None`
  반환 키: `{"esop": int, "inst": int, "retail": int}`. 우리사주 없으면 `esop=0`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# 마키나락스 실측: 우리사주 349,300 / 기관 1,626,950 / 일반 658,750
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_impl_report_parser.py -k allocation -v`
Expected: FAIL — `AttributeError: ... has no attribute 'parse_allocation_table'`

- [ ] **Step 3: 구현**

```python
ALLOC_LABELS = {"우리사주조합": "esop", "기관투자자": "inst", "일반투자자": "retail"}


def _final_alloc_qty(cells: list[str]) -> int:
    """최종 배정수량 = 뒤에서 세 번째 수량 셀.

    행 끝이 (수량, 금액, 비율) 순서이므로 수량형 셀을 뒤에서 훑어
    3번째로 만나는 것이 최종 배정수량이다. 전부 '-'인 행은 0.
    """
    qtys = [q for q in (parse_qty(c) for c in reversed(cells[1:])) if q is not None]
    if len(qtys) >= 3:
        return qtys[2]
    return qtys[-1] if qtys else 0


def parse_allocation_table(text: str) -> dict | None:
    """「청약 및 배정현황」 표에서 그룹별 최종 배정수량을 파싱."""
    out = {}
    for cells in extract_rows(text):
        if len(cells) < 2:
            continue
        key = ALLOC_LABELS.get(WS_RE.sub("", cells[0]))
        if key is None:
            continue
        out[key] = _final_alloc_qty(cells)
    if "inst" not in out:
        return None
    out.setdefault("esop", 0)
    out.setdefault("retail", 0)
    return out
```

> `_final_alloc_qty` 의 "뒤에서 3번째" 가정은 `test_parse_allocation_inst_matches_lockup_total`
> 과 Task 7의 게이트 ③으로 이중 검증된다. 실수집에서 불일치가 나오면 그 건은 `failed` 로 빠지며
> 조용히 잘못된 값이 들어가지 않는다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_impl_report_parser.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: 커밋**

```bash
git add impl_report_parser.py tests/test_impl_report_parser.py
git commit -m "feat: 청약·배정현황 파서 (우리사주·기관 최종배정)"
```

---

### Task 5: 증권발행실적보고서 수집 드라이버

**Files:**
- Create: `collect_impl_reports.py`
- Test: `tests/test_collect_impl_reports.py`

**Interfaces:**
- Consumes: `impl_report_parser.parse_lockup_table` / `parse_allocation_table` / `decode_document` (Task 2-4), `perf_common` (Task 1), `pipeline.DART_API_KEY`
- Produces:
  - `find_impl_report(corp_code, listing_date) -> dict | None` — `{"rcept_no","report_nm"}`, 정정본 우선
  - `main(limit=None)` — 955사 루프, `impl_reports` 적재

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_collect_impl_reports.py` 생성:

```python
import types

import pytest

import collect_impl_reports as cir


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_find_impl_report_prefers_latest_correction(monkeypatch):
    """[기재정정]이 있으면 접수번호가 큰 최신본을 쓴다."""
    payload = {"status": "000", "list": [
        {"report_nm": "증권발행실적보고서", "rcept_no": "20241031000328"},
        {"report_nm": "[기재정정]증권발행실적보고서", "rcept_no": "20241031000452"},
        {"report_nm": "투자설명서", "rcept_no": "20241025000263"},
    ]}
    monkeypatch.setattr(cir, "_fetch_with_retry",
                        lambda *a, **k: _FakeResp(payload))
    r = cir.find_impl_report("01573336", "2024-11-07")
    assert r["rcept_no"] == "20241031000452"


def test_find_impl_report_returns_none_when_absent(monkeypatch):
    """공모 없는 상장(이전상장 등)은 실적보고서가 없다 → None (결측 아님)."""
    payload = {"status": "000", "list": [
        {"report_nm": "투자설명서", "rcept_no": "20241025000263"}]}
    monkeypatch.setattr(cir, "_fetch_with_retry",
                        lambda *a, **k: _FakeResp(payload))
    assert cir.find_impl_report("01573336", "2024-11-07") is None


def test_find_impl_report_raises_on_quota(monkeypatch):
    """DART 한도 초과는 조용히 넘기면 안 된다."""
    monkeypatch.setattr(cir, "_fetch_with_retry",
                        lambda *a, **k: _FakeResp({"status": "020", "message": "한도초과"}))
    with pytest.raises(RuntimeError, match="한도"):
        cir.find_impl_report("01573336", "2024-11-07")


def test_search_window_spans_listing_date():
    """검색창은 상장 4개월 전 ~ 1개월 후. 연도 경계를 넘어도 깨지지 않아야 한다."""
    bgn, end = cir.search_window("2024-02-10")
    assert bgn == "20231010"
    assert end == "20240310"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_collect_impl_reports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collect_impl_reports'`

- [ ] **Step 3: 구현**

`collect_impl_reports.py` 생성:

```python
"""DART 증권발행실적보고서 수집 → impl_reports.

증권발행실적보고서에는 「기관투자자 의무보유확약기간별 배정현황」이 실려 있다.
38커뮤니케이션의 확약비율(수요예측 신청수량 기준)과 달리 이 값은 배정수량 기준이며,
확약기관 우선배정 때문에 항상 신청기준보다 높다.

공모 없는 상장(코넥스 이전상장 등)은 이 보고서 자체가 없다. 결측이 아니라
개념상 해당 없음이므로 parse_status='na' 로 구분해 기록한다.
"""
import argparse
import datetime
import io
import time
import zipfile

import requests

import impl_report_parser as irp
import perf_common as pc
from pipeline import DART_API_KEY

LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
LIMIT_STATUSES = {"020", "800"}


def _fetch_with_retry(url, params, timeout=30):
    """collect_quarterly._fetch_with_retry와 동일한 5/30/120초 백오프."""
    waits = [5, 30, 120]
    for attempt in range(4):
        try:
            return requests.get(url, params=params, timeout=timeout)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            if attempt == 3:
                raise
            print(f"[RETRY] Attempt {attempt+1} failed ({type(e).__name__}). "
                  f"Waiting {waits[attempt]}s...", flush=True)
            time.sleep(waits[attempt])


def search_window(listing_date: str) -> tuple[str, str]:
    """상장일 기준 4개월 전 ~ 1개월 후 (YYYYMMDD)."""
    y, m, d = (int(x) for x in listing_date.split("-"))
    base = y * 12 + (m - 1)
    b, e = base - 4, base + 1
    return f"{b // 12:04d}{b % 12 + 1:02d}01", f"{e // 12:04d}{e % 12 + 1:02d}28"


def find_impl_report(corp_code: str, listing_date: str) -> dict | None:
    """증권발행실적보고서를 찾는다. 정정본이 있으면 접수번호가 가장 큰 것."""
    bgn, end = search_window(listing_date)
    resp = _fetch_with_retry(LIST_URL, {
        "crtfc_key": DART_API_KEY, "corp_code": corp_code,
        "bgn_de": bgn, "end_de": end, "page_count": 100})
    time.sleep(0.15)
    data = resp.json()
    status = data.get("status")
    if status in LIMIT_STATUSES:
        raise RuntimeError(
            f"DART API 한도 초과 (status={status}, msg={data.get('message')}) "
            f"corp_code={corp_code}")
    if status == "013":
        return None
    if status != "000":
        print(f"[WARN] DART status={status} corp_code={corp_code} — skip")
        return None
    items = [x for x in data.get("list", [])
             if "증권발행실적" in x.get("report_nm", "")]
    if not items:
        return None
    latest = max(items, key=lambda x: x["rcept_no"])
    return {"rcept_no": latest["rcept_no"], "report_nm": latest["report_nm"]}


def fetch_document(rcept_no: str) -> str:
    """원문 zip을 받아 첫 xml을 디코딩해 반환."""
    resp = _fetch_with_retry(DOC_URL, {
        "crtfc_key": DART_API_KEY, "rcept_no": rcept_no})
    time.sleep(0.15)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    return irp.decode_document(zf.read(zf.namelist()[0]))


def main(limit=None):
    con = pc.get_db()
    pc.ensure_tables(con)
    rows = con.execute(
        """SELECT dart_corp_code, 회사명, 상장일 FROM ipo_companies
           WHERE (상장유형 IS NULL OR 상장유형!='SPAC')
             AND dart_corp_code IS NOT NULL
           ORDER BY 상장일""").fetchall()
    done = {r[0] for r in con.execute(
        "SELECT corp_code FROM impl_reports WHERE parse_status IN ('ok','na')")}
    todo = [r for r in rows if r[0] not in done][:limit]
    print(f"대상 {len(todo)}사 (완료 {len(done)}사 스킵)")

    now = datetime.datetime.now().isoformat(timespec="seconds")
    for i, (corp, name, ld) in enumerate(todo, 1):
        found = find_impl_report(corp, ld)
        if found is None:
            con.execute(
                """INSERT OR REPLACE INTO impl_reports
                   (corp_code, parse_status, fetched_at) VALUES (?,'na',?)""",
                (corp, now))
            con.commit()
            print(f"[{i}/{len(todo)}] {name} — 실적보고서 없음(na)")
            continue
        try:
            text = fetch_document(found["rcept_no"])
            lock = irp.parse_lockup_table(text)
            alloc = irp.parse_allocation_table(text)
        except Exception as e:
            print(f"[{i}/{len(todo)}] {name} — 파싱실패: {type(e).__name__} {e}")
            con.execute(
                """INSERT OR REPLACE INTO impl_reports
                   (corp_code, rcept_no, parse_status, fetched_at)
                   VALUES (?,?,'error',?)""", (corp, found["rcept_no"], now))
            con.commit()
            continue

        status = "ok" if (lock and alloc) else "partial"
        con.execute(
            """INSERT OR REPLACE INTO impl_reports
               (corp_code, rcept_no, report_nm, inst_alloc, esop, retail_alloc,
                lockup_none, lockup_15d, lockup_1m, lockup_3m, lockup_6m,
                parse_status, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (corp, found["rcept_no"], found["report_nm"],
             (alloc or {}).get("inst"), (alloc or {}).get("esop"),
             (alloc or {}).get("retail"),
             (lock or {}).get("none"), (lock or {}).get("15d"),
             (lock or {}).get("1m"), (lock or {}).get("3m"),
             (lock or {}).get("6m"), status, now))
        con.commit()
        print(f"[{i}/{len(todo)}] {name} {status} "
              f"확약={(lock or {}).get('locked')}/{(lock or {}).get('total')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    main(ap.parse_args().limit)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_collect_impl_reports.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 실데이터 3건 스모크 테스트**

Run: `python3 collect_impl_reports.py --limit 3`
Expected: 3건이 `ok` 또는 `na` 로 출력되고 예외 없이 종료

- [ ] **Step 6: 커밋**

```bash
git add collect_impl_reports.py tests/test_collect_impl_reports.py
git commit -m "feat: 증권발행실적보고서 수집 드라이버 (증분·정정본우선·na구분)"
```

- [ ] **Step 7: 전수 수집 실행**

Run: `python3 collect_impl_reports.py`
Expected: 955사 처리. 소요 ~20분. 중단되면 재실행하면 이어서 진행된다.

수집 후 커버리지 확인:

```bash
python3 -c "
import sqlite3, collections
con = sqlite3.connect('ipo_data.db')
c = collections.Counter(r[0] for r in con.execute('SELECT parse_status FROM impl_reports'))
print(c)
"
```

---

### Task 6: A(보호예수) 추출 드라이버

`verify_float_extractor` 는 wrong-confident 0건으로 검증되었으나 **그 골든셋은 2024년 이후 172건뿐이다.**
2026-07-28 전기간 사전스캔 실측:

```
연도   n   confident  ambiguous  캐시없음
2016  120     42        40        38
2017   92     35        33        24
2018   99     34        48        17
2019   94     40        35        19
2020   82      3        65        14     ← 이상 저조
2021   98      1        86        11     ← 이상 저조
2022   85     27        44        14
2023   99     77         8        14
2024   86     66        13         7
2025   80     72         4         4
2026   20     18         1         1
합계  955    415       377       163
confident 43.5% (캐시보유분 대비 52.4%)
```

두 가지 문제가 드러났다.

**① 구시대 구간 wrong-confident 미검증.** 기존값과 추출값을 더하면 90~107%가 되는 역전 사례가 있다
(신라젠 13.85→75.14, 퓨쳐켐 9.78→63.64, 엠에프엠코리아 14.29→92.81).
추출기가 보호예수 비율을 유통비율로 잡았을 가능성이 있으며, 2024+ 골든셋으로는 검증되지 않는다.
→ Step 5에서 구간별 골든셋을 별도로 만든다.

**② 캐시 부재 163건 + 2020~21 구간 붕괴.** 2020~21의 confident가 4/180인 것은
그 시기 투자설명서 표 형식이 다르다는 신호다. 원인 조사는 Step 7에서 한다.

이 태스크는 새 추출 로직을 만들지 않고 **전기간 적용 드라이버 + 구간별 검증**을 추가한다.

**Files:**
- Create: `extract_float_all.py`
- Test: `tests/test_extract_float_all.py`

**Interfaces:**
- Consumes: `verify_float_extractor.extract_for_company`, `perf_common`
- Produces: `float_extractions` 임시 테이블 (`corp_code`, `float_pct`, `verdict`, `detail`)
  및 `run(limit=None) -> dict` (요약 카운트)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_extract_float_all.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
"""verify_float_extractor를 전기간(955사)에 적용해 float_extractions에 적재.

verify_float_extractor는 confident일 때만 값을 내고 애매하면 ambiguous로 빠진다
(2026-07-28 캘리브레이션: 160/172, wrong-confident 0건). 따라서 confident 판정은
추가 검증 없이 채택해도 안전하다.
"""
import argparse
import collections

import perf_common as pc
import verify_float_extractor as vf

DDL = """CREATE TABLE IF NOT EXISTS float_extractions(
    corp_code TEXT PRIMARY KEY, float_pct REAL, verdict TEXT, detail TEXT)"""


def summarize(rows) -> dict:
    c = collections.Counter(r["verdict"] for r in rows)
    return {"confident": c["confident"], "ambiguous": c["ambiguous"],
            "total": len(rows)}


def run(limit=None) -> dict:
    con = pc.get_db()
    con.execute(DDL)
    rows = con.execute(
        """SELECT 회사명, dart_corp_code, 상장후주식수 FROM ipo_companies
           WHERE (상장유형 IS NULL OR 상장유형!='SPAC')
             AND dart_corp_code IS NOT NULL
           ORDER BY 상장일""").fetchall()[:limit]
    out = []
    for i, (name, corp, total) in enumerate(rows, 1):
        try:
            verdict, value, detail, _ = vf.extract_for_company(name, total)
        except Exception as e:
            verdict, value, detail = "ambiguous", None, f"error:{type(e).__name__}"
        con.execute(
            "INSERT OR REPLACE INTO float_extractions VALUES (?,?,?,?)",
            (corp, value, verdict, detail))
        out.append({"verdict": verdict, "value": value})
        if i % 100 == 0:
            con.commit()
            print(f"  ...{i}/{len(rows)}", flush=True)
    con.commit()
    s = summarize(out)
    print(f"confident {s['confident']}/{s['total']} "
          f"({s['confident']/max(1,s['total'])*100:.1f}%), "
          f"ambiguous {s['ambiguous']}")
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    run(ap.parse_args().limit)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_extract_float_all.py -v`
Expected: PASS

- [ ] **Step 5: 투설 캐시 보강 (163건)**

`docs/<회사명>/` 에 문서가 없는 163건을 내려받는다. `dart_rcept_no` 가 가리키는 투자설명서를
`collect_impl_reports.fetch_document` 로 받아 같은 규칙으로 저장한다.

```python
# fill_prospectus_cache.py
"""투설 캐시가 없는 건을 dart_rcept_no로 내려받아 docs/<회사명>/<rcept_no>.xml 로 저장."""
import os

import collect_impl_reports as cir
import perf_common as pc

DOCS = pc.ROOT / "docs"


def main():
    con = pc.get_db()
    rows = con.execute(
        """SELECT 회사명, dart_rcept_no FROM ipo_companies
           WHERE (상장유형 IS NULL OR 상장유형!='SPAC')
             AND dart_rcept_no IS NOT NULL ORDER BY 상장일""").fetchall()
    n = 0
    for name, rcept in rows:
        d = DOCS / name
        if d.is_dir() and any(f.endswith(".xml") for f in os.listdir(d)):
            continue
        try:
            text = cir.fetch_document(rcept)
        except Exception as e:
            print(f"  {name}: 실패 {type(e).__name__}")
            continue
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{rcept}.xml").write_text(text, encoding="utf-8")
        n += 1
        print(f"[{n}] {name} 저장")
    print(f"총 {n}건 보강")


if __name__ == "__main__":
    main()
```

Run: `python3 fill_prospectus_cache.py`
Expected: 캐시 없던 건들이 채워진다. `dart_rcept_no` 자체가 없는 건은 남는다.

> 주의: `verify_float_extractor.find_doc_path` 는 폴더 안 xml이 **정확히 1개**일 때만 경로를 반환한다.
> 기존 폴더에 파일을 추가하면 안 되고, 비어 있는 폴더에만 저장해야 한다. 위 코드는 그 조건을 지킨다.

- [ ] **Step 6: 2024+ 골든셋 게이트 확인**

Run: `python3 verify_float_extractor.py --calibrate | head -3`
Expected: `confident인데 틀린 건(위험): 0건` — **0이 아니면 즉시 중단하고 보고할 것**

- [ ] **Step 7: 구간별 골든셋 구축 (2016~2021, 20건)**

2024+ 골든셋은 구시대 문서를 대표하지 않는다. 2016~2021 구간에서 `confident` 판정을 받은 건 중
**20건을 무작위 추출해 원문을 직접 읽고** 수기 검증한다. 특히 추출값이 60% 이상인 건을 우선 포함한다
(보호예수 비율 오채택 의심 구간).

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('ipo_data.db')
q = '''SELECT c.회사명, c.상장일, f.float_pct, c.유통가능주식수비율
       FROM float_extractions f JOIN ipo_companies c ON c.dart_corp_code=f.corp_code
       WHERE f.verdict='confident' AND c.상장일 < '2022-01-01'
       ORDER BY (f.float_pct > 60) DESC, RANDOM() LIMIT 20'''
for r in con.execute(q):
    print(f'{r[1]} {r[0][:14]:16s} 추출={r[2]:>6} 기존={r[3]}')
"
```

각 건의 원문에서 "상장 직후 유통가능 주식수" 표를 찾아 실제 값을 확인하고,
`data_corrections` 에 `field='유통가능주식수비율_구간검증'` 으로 기록한다.

**합격 기준: wrong-confident 0건.** 1건이라도 나오면 해당 시기 문서에 대해
`extract_for_company` 결과를 신뢰할 수 없으므로, 그 구간 전체를 `ambiguous` 로 강등하는
가드를 `extract_float_all.py` 에 추가하고 다시 측정한다.

- [ ] **Step 8: 전수 실행 및 커밋**

```bash
python3 extract_float_all.py
git add extract_float_all.py fill_prospectus_cache.py tests/test_extract_float_all.py
git commit -m "feat: 보호예수 추출 전기간 드라이버 + 캐시 보강"
```

- [ ] **Step 9: 2020~2021 붕괴 원인 조사**

사전스캔에서 2020~21의 confident가 4/180으로 유독 낮았다. 캐시 보강 후에도 개선되지 않으면
해당 연도 문서 3건의 유통가능물량 표를 직접 열어 형식 차이를 확인하고 결과를 기록한다.

```bash
python3 -c "
import sqlite3, verify_float_extractor as vf
con = sqlite3.connect('ipo_data.db')
for name, total in con.execute('''SELECT 회사명, 상장후주식수 FROM ipo_companies
        WHERE 상장일 BETWEEN '2020-01-01' AND '2021-12-31'
          AND (상장유형 IS NULL OR 상장유형!='SPAC') LIMIT 3'''):
    v, val, detail, path = vf.extract_for_company(name, total)
    print(f'{name}: {v} {val} ({detail}) {path}')
"
```

원인이 파서 수정으로 해결 가능하면 수정하고, 아니면 해당 구간을 `failed` 로 두고
`## 미해결 항목` 에 규모를 명시한다. **추정값으로 채우지 않는다.**

---

### Task 7: 항등식 병합 + 4중 검증

**Files:**
- Create: `build_share_structure.py`
- Test: `tests/test_build_share_structure.py`

**Interfaces:**
- Consumes: `impl_reports` (Task 5), `float_extractions` (Task 6), `ipo_companies`
- Produces:
  - `compute_structure(row: dict) -> dict` — 순수 함수. A/B/C/D + `identity_gap` + `verdict` 산출
  - `main()` — `share_structure` 적재

산출 규칙:
```
total   = ipo_companies.상장후주식수
B       = impl_reports.inst_alloc - impl_reports.lockup_none
C       = impl_reports.esop
투설유통 = float_extractions.float_pct / 100 * total       (A와 C를 뺀 값)
A       = total - 투설유통 - C
D       = 투설유통 - B
```

> **항등식은 게이트로 쓸 수 없다.** A를 `total − 투설유통 − C` 로 역산하므로
> `A+B+C+D = (total−pf−C) + B + C + (pf−B) = total` 이 대수적으로 항상 성립한다.
> 즉 `identity_gap` 은 언제나 0이며 아무것도 검증하지 못한다.
> 컬럼은 향후 A를 독립 추출하게 될 때를 위해 남기되, **게이트는 아래 4종으로 구성한다.**

| 게이트 | 내용 | 무엇을 잡는가 |
|---|---|---|
| ① 부호 | `A ≥ 0`, `B ≥ 0`, `D ≥ 0` | 투설유통 < 확약 → 투설값 또는 확약값 오류 |
| ② 범위 | `D/total ∈ [3%, 85%]` | 보호예수 비율을 유통비율로 오채택한 케이스 |
| ③ 확약 내부 | `B ≤ 기관배정`, `15d+1m+3m+6m == B` | 확약표 합계열 오선택 |
| ④ 38 교차 | `38신청기준 ≤ 배정기준 + 1.0%p` | **독립 소스 간 대조 — 유일한 진짜 외부 검증** |

④가 핵심이다. 38커뮤니케이션과 DART는 완전히 독립된 소스이고, 확약기관 우선배정 때문에
신청기준이 배정기준을 넘을 수 없다. 이 부등식이 깨지면 둘 중 하나가 틀렸다는 뜻이다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import build_share_structure as bss

# 마키나락스 실측 (설계문서 §1.1). lockup_38은 38커뮤니케이션 신청기준 확약률.
MAKINA = {
    "corp_code": "01709065", "listing_date": "2026-05-20",
    "total_shares": 18_255_368, "float_pct": 38.48, "float_verdict": "confident",
    "inst_alloc": 1_626_950, "lockup_none": 29_439, "esop": 349_300,
    "lockup_15d": 83_150, "lockup_1m": 151_465,
    "lockup_3m": 520_076, "lockup_6m": 842_820, "lockup_38": 78.17,
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
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_gate_skipped_when_38_missing():
    """38 값 결측은 탈락 사유가 아니다 — 게이트 ④를 건너뛴다."""
    assert bss.compute_structure(dict(MAKINA, lockup_38=None))["verdict"] == "auto_ok"


def test_gate_rejects_lockup_exceeding_allocation():
    """게이트 ③: 확약이 기관배정을 넘으면 failed."""
    bad = dict(MAKINA, lockup_none=-100)                # locked > inst_alloc
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_gate_rejects_out_of_range_float():
    """게이트 ②: 실유통이 [3%, 85%] 밖이면 failed."""
    bad = dict(MAKINA, float_pct=95.0)
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_gate_rejects_ambiguous_float():
    """A 추출이 ambiguous면 추정하지 않고 failed."""
    bad = dict(MAKINA, float_verdict="ambiguous", float_pct=None)
    assert bss.compute_structure(bad)["verdict"] == "failed"


def test_na_when_no_public_offering():
    """공모 없는 상장은 na — 결측(failed)과 구분한다."""
    na = dict(MAKINA, inst_alloc=None, lockup_none=None, esop=None)
    assert bss.compute_structure(na)["verdict"] == "na"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_build_share_structure.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
"""impl_reports + float_extractions를 항등식으로 병합해 share_structure 적재.

    상장예정주식수 = A 보호예수 + B 기관확약 + C 우리사주 + D 실유통

투자설명서의 유통가능물량 표는 공모 전에 작성되므로 수요예측 후 확정되는
기관 확약(B)을 반영하지 못한다. 그래서 투설 유통비율은 항상 과대계상이며
과대 폭이 확약률에 비례한다. D는 여기서 B를 차감해 산출한다.
"""
import argparse
import datetime

import perf_common as pc

FLOAT_MIN, FLOAT_MAX = 3.0, 85.0
GATE4_TOL = 1.0             # %p — 38 신청기준이 배정기준을 초과할 수 있는 허용오차


def compute_structure(row: dict) -> dict:
    """A/B/C/D와 검증 결과를 산출. 순수 함수."""
    total = row.get("total_shares")
    out = {"corp_code": row["corp_code"], "listing_date": row.get("listing_date"),
           "total_shares": total, "lockup_existing": None, "lockup_inst": None,
           "esop": None, "free_float": None, "free_float_pct": None,
           "inst_alloc": row.get("inst_alloc"), "lockup_inst_pct": None,
           "lockup_15d": row.get("lockup_15d"), "lockup_1m": row.get("lockup_1m"),
           "lockup_3m": row.get("lockup_3m"), "lockup_6m": row.get("lockup_6m"),
           "identity_gap": None, "verdict": "failed",
           "evidence": row.get("float_detail")}

    inst, none_q, esop = (row.get("inst_alloc"), row.get("lockup_none"),
                          row.get("esop"))
    # 공모 자체가 없는 상장(이전상장 등) — 결측이 아니라 개념상 해당 없음
    if inst is None and none_q is None:
        out["verdict"] = "na"
        return out

    if (total is None or inst is None or none_q is None or esop is None
            or row.get("float_verdict") != "confident"
            or row.get("float_pct") is None):
        return out

    b = inst - none_q                          # B 기관확약
    prospectus_float = row["float_pct"] / 100 * total   # 투설 유통가능 (A·C 제외분)
    a = total - prospectus_float - esop        # A 보호예수
    d = prospectus_float - b                   # D 실유통

    out.update({
        "lockup_existing": round(a), "lockup_inst": b, "esop": esop,
        "free_float": round(d), "free_float_pct": d / total * 100,
        "lockup_inst_pct": b / inst * 100 if inst else None,
    })
    # A를 역산하므로 이 값은 항상 0이다. 게이트가 아니라 기록용이며,
    # 훗날 A를 독립 추출하게 되면 그때 게이트로 승격한다.
    out["identity_gap"] = abs((a + b + esop + d) - total) / total * 100

    # ① 부호: 투설유통 < 확약이면 둘 중 하나가 틀렸다
    if a < 0 or b < 0 or d < 0:
        return out
    # ② 범위: 보호예수 비율을 유통비율로 오채택한 케이스를 걸러낸다
    if not (FLOAT_MIN <= out["free_float_pct"] <= FLOAT_MAX):
        return out
    # ③ 확약 내부 정합
    if b > inst:
        return out
    parts = sum(row.get(k) or 0 for k in
                ("lockup_15d", "lockup_1m", "lockup_3m", "lockup_6m"))
    if parts and abs(parts - b) > 1:           # 확약기간별 합 == B
        return out
    # ④ 38 교차검증: 확약기관 우선배정 구조상 신청기준 > 배정기준은 불가능.
    #    독립된 두 소스를 맞대는 유일한 외부 검증이다.
    lk38 = row.get("lockup_38")
    if (lk38 is not None and out["lockup_inst_pct"] is not None
            and lk38 > out["lockup_inst_pct"] + GATE4_TOL):
        return out

    out["verdict"] = "auto_ok"
    return out


SRC_SQL = """
SELECT c.dart_corp_code AS corp_code, c.상장일 AS listing_date,
       c.상장후주식수 AS total_shares,
       c.의무보유확약비율 AS lockup_38,
       f.float_pct, f.verdict AS float_verdict, f.detail AS float_detail,
       i.inst_alloc, i.esop, i.lockup_none,
       i.lockup_15d, i.lockup_1m, i.lockup_3m, i.lockup_6m, i.rcept_no
FROM ipo_companies c
LEFT JOIN float_extractions f ON f.corp_code = c.dart_corp_code
LEFT JOIN impl_reports i      ON i.corp_code = c.dart_corp_code
WHERE (c.상장유형 IS NULL OR c.상장유형!='SPAC') AND c.dart_corp_code IS NOT NULL
ORDER BY c.상장일
"""


def main():
    con = pc.get_db()
    pc.ensure_tables(con)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    counts = {}
    for r in con.execute(SRC_SQL):
        res = compute_structure(dict(r))
        counts[res["verdict"]] = counts.get(res["verdict"], 0) + 1
        con.execute(
            """INSERT OR REPLACE INTO share_structure
               (corp_code, listing_date, total_shares, lockup_existing,
                lockup_inst, esop, free_float, free_float_pct, inst_alloc,
                lockup_inst_pct, lockup_15d, lockup_1m, lockup_3m, lockup_6m,
                identity_gap, verdict, src_impl_rcept, src_prosp_rcept,
                evidence, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (res["corp_code"], res["listing_date"], res["total_shares"],
             res["lockup_existing"], res["lockup_inst"], res["esop"],
             res["free_float"], res["free_float_pct"], res["inst_alloc"],
             res["lockup_inst_pct"], res["lockup_15d"], res["lockup_1m"],
             res["lockup_3m"], res["lockup_6m"], res["identity_gap"],
             res["verdict"], r["rcept_no"], None, res["evidence"], now))
    con.commit()
    total = sum(counts.values())
    print(f"총 {total}사: " + ", ".join(
        f"{k}={v}({v/total*100:.1f}%)" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_build_share_structure.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 실행 및 성공기준 확인**

Run: `python3 build_share_structure.py`

성공기준은 **구간별로 다르게** 둔다. 사전스캔 실측(전기간 confident 43.5%)상
단일 기준 70%는 달성 불가능하며, 무리하게 맞추려 하면 추정값을 채우는 유혹이 생긴다.

| 구간 | `auto_ok` 기준 | 근거 |
|---|---|---|
| 2024-01 이후 (186사) | **≥ 75%** | 사전스캔 confident ~85%, 항등식 탈락분 감안 |
| 전기간 (955사) | **≥ 40%** | 사전스캔 43.5% + 캐시보강분 − 항등식 탈락분 |

전기간 기준을 낮게 잡는 것은 데이터 품질을 포기하는 게 아니다. `failed` 는 분석에서 제외되므로
**커버리지가 낮아도 남은 값은 정확하다**. 반대로 기준을 억지로 맞추면 오염이 들어간다.

구간별 확인:

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('ipo_data.db')
q = '''SELECT CASE WHEN listing_date >= '2024-01-01' THEN '2024+' ELSE '~2023' END g,
       verdict, COUNT(*) FROM share_structure GROUP BY g, verdict ORDER BY g, 3 DESC'''
for r in con.execute(q):
    print(r)
"
```

미달이면 `failed` 사유를 분해해 보고한다:

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('ipo_data.db')
for r in con.execute('''SELECT verdict, COUNT(*) FROM share_structure
                        GROUP BY verdict ORDER BY 2 DESC'''):
    print(r)
"
```

- [ ] **Step 6: 3개사 대조 검증**

설계문서 §1.1 표와 일치하는지 확인한다.

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('ipo_data.db'); con.row_factory = sqlite3.Row
for nm, cc in [('마키나락스','01709065'), ('토모큐브','01573336'), ('에이치브이엠','01011368')]:
    r = con.execute('SELECT * FROM share_structure WHERE corp_code=?', (cc,)).fetchone()
    if r:
        print(f\"{nm}: 실유통={r['free_float_pct']:.2f}% 확약률={r['lockup_inst_pct']:.1f}% {r['verdict']}\")
"
```
Expected: 마키나락스 29.73% / 토모큐브 32.04% / 에이치브이엠 28.15% (±0.1%p)

- [ ] **Step 7: 우리사주 이중계상 진단 (스펙 §5.2)**

투자설명서의 유통가능물량 표가 우리사주(C)를 **유통가능으로 분류했다면** `투설유통(pf)` 에 C가
섞이고, `D = pf − B` 이므로 **주지표 D가 그만큼 과대계상**된다. C가 D에 미치는 영향은
간접적이지만 실재하므로 반드시 확인한다.

우리사주가 있는 딜과 없는 딜의 실유통비율 분포를 비교한다. 표가 C를 제대로 제외했다면
두 집단의 D 분포에 체계적 차이가 없어야 한다.

```bash
python3 -c "
import sqlite3, statistics as st
con = sqlite3.connect('ipo_data.db')
q = '''SELECT esop, free_float_pct, total_shares FROM share_structure
       WHERE verdict='auto_ok' AND free_float_pct IS NOT NULL'''
has, non = [], []
for esop, ff, tot in con.execute(q):
    (has if (esop or 0) > 0 else non).append(ff)
print(f'우리사주 있음 n={len(has)} 중앙값={st.median(has):.2f}%' if has else '없음')
print(f'우리사주 없음 n={len(non)} 중앙값={st.median(non):.2f}%' if non else '없음')
if has and non:
    print(f'차이={st.median(has)-st.median(non):+.2f}%p')
"
```

판정:
- 차이가 **±2%p 이내** → C가 정상적으로 제외된 것. 그대로 진행
- 우리사주 있는 집단이 **뚜렷하게 높음** → 표가 C를 유통가능에 포함한 것.
  `compute_structure` 의 `d = prospectus_float - b` 를 `d = prospectus_float - b - esop` 로
  바꾸고 Step 6의 3개사 대조를 다시 통과시킨다

결과를 수치와 함께 기록한다. 어느 쪽이든 판단 근거가 남아야 한다.

- [ ] **Step 8: 커밋**

```bash
git add build_share_structure.py tests/test_build_share_structure.py
git commit -m "feat: 물량 항등식 병합 + 4중 검증 게이트"
```

---

### Task 8: 리포트 전환

**Files:**
- Modify: `perf_common.py:10-23` (`UNIVERSE_SQL`)
- Modify: `build_scatter_pack.py:25-40` (`VARIABLES`), `:239-255` (`main`의 정정 훅)
- Test: `tests/test_perf_common.py`

**Interfaces:**
- Consumes: `share_structure` (Task 7)
- Produces: `load_universe()` 결과에 `free_float_pct`, `lockup_inst_pct` 포함

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_universe_sql_exposes_new_metrics():
    """유니버스에 실유통비율·배정기준확약률이 포함된다."""
    import perf_common as pc
    con = pc.get_db()
    rows = pc.load_universe(con)
    assert rows, "유니버스가 비어 있음"
    for key in ("free_float_pct", "lockup_inst_pct"):
        assert key in rows[0], f"missing {key}"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_perf_common.py -k universe_sql_exposes -v`
Expected: FAIL — `AssertionError: missing free_float_pct`

- [ ] **Step 3: UNIVERSE_SQL 수정**

`perf_common.py` 의 `UNIVERSE_SQL` 에서 `FROM ipo_companies` 앞 SELECT 목록 끝에 두 줄을 추가하고,
`FROM` 절에 LEFT JOIN을 건다:

```sql
       "확정공모금액_억원" AS offer_size, "신주" AS new_shares, "구주" AS old_shares,
       s.free_float_pct, s.lockup_inst_pct, s.verdict AS structure_verdict
FROM ipo_companies
LEFT JOIN share_structure s ON s.corp_code = ipo_companies.dart_corp_code
WHERE "상장일" >= '2024-01-01'
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_perf_common.py -v`
Expected: PASS

- [ ] **Step 5: 산점도 변수 교체**

`build_scatter_pack.py` 의 `VARIABLES` 리스트에서 첫 두 항목을 교체한다:

```python
VARIABLES = [
    ("free_float_pct", "상장일 실유통비율", "%", False),
    ("lockup_inst_pct", "의무보유확약비율(배정기준)", "%", False),
    ("lockup_ratio", "의무보유확약비율(38·신청기준)", "%", False),
    ("inst_ratio", "기관경쟁률", ":1", True),
    # ... 이하 기존 항목 유지
```

`main()` 의 `data_corrections` 정정 훅(245-255행)은 `float_ratio` 를 고치던 것으로,
이제 `free_float_pct` 가 정본이므로 **삭제한다**. 대신 `structure_verdict != 'auto_ok'` 인
건을 제외하는 필터를 넣는다:

```python
    # 검증 통과분만 사용 (failed/na는 분석에서 제외)
    before = len(df)
    df.loc[df["structure_verdict"] != "auto_ok",
           ["free_float_pct", "lockup_inst_pct"]] = np.nan
    n_ok = (df["structure_verdict"] == "auto_ok").sum()
    print(f"물량구조 검증통과 {n_ok}/{before}사 — 미통과분은 해당 변수만 NaN 처리")
```

- [ ] **Step 6: 리포트 재생성**

Run: `python3 build_scatter_pack.py`
Expected: `compare_report/ipo_scatter_pack.pdf` 생성. 페이지에 새 변수 2종이 나타난다.

- [ ] **Step 7: 상관 변화 기록**

새 지표와 기존 지표의 상관을 비교해 결론 변화를 확인한다.

```bash
python3 -c "
import pandas as pd, perf_common as pc
con = pc.get_db()
df = pd.DataFrame(pc.load_universe(con))
px = pd.read_sql('''SELECT stock_code,horizon,excess_return FROM price_performance
                    WHERE base_price_type=\"IPO\"''', con).pivot(
    index='stock_code', columns='horizon', values='excess_return')
t = pc.corp_to_stock_map(); df['sc'] = df['corp_code'].map(t)
df = df.merge(px, left_on='sc', right_index=True, how='left')
for var in ['float_ratio','free_float_pct','lockup_ratio','lockup_inst_pct']:
    for h in ['1M','6M']:
        m = df[[var,h]].dropna()
        if len(m) > 10:
            print(f'{var:18s} {h}: rho={m[var].rank().corr(m[h].rank()):+.3f} n={len(m)}')
"
```

- [ ] **Step 8: 커밋**

```bash
git add perf_common.py build_scatter_pack.py tests/test_perf_common.py
git commit -m "feat: 리포트를 실유통비율·배정기준확약률로 전환"
```

---

## 미해결 항목 (별도 처리)

| 항목 | 사유 |
|---|---|
| Haiku fallback (스펙 §3.2 2순위) | `ANTHROPIC_API_KEY` 미설정. Task 6까지의 `ambiguous` 잔여 규모를 확인한 뒤 필요성을 재판단한다. 1순위만으로 성공기준을 충족하면 불필요 |
| 해제 스케줄(시점별 유통물량 곡선) | 스펙 §2.1에서 별도 프로젝트로 분리. `lockup_15d/1m/3m/6m` 컬럼에 원천 데이터는 이미 적재됨 |
| 2016~2023 `유통가능주식수비율` 기존 컬럼 | 오염 상태로 잔존. `share_structure` 가 정본이 되므로 기존 컬럼은 참조하지 않는다 |
| 2020~2021 구간 추출 붕괴 | 사전스캔 confident 4/180. Task 6 Step 9에서 원인을 조사하되, 파서 수정으로 해결되지 않으면 `failed` 로 두고 규모를 명시한다 |
| 구간별 골든셋 20건 | Task 6 Step 7에서 수기 구축. 2024+ 골든셋이 구시대 문서를 대표하지 못하는 문제에 대한 대응이며, 이 검증 없이는 2016~2021 값을 신뢰할 수 없다 |
| `identity_gap` 컬럼 | 현재 A 역산 구조에서는 항상 0이라 검증력이 없다. A를 투설에서 독립 추출하도록 개선하면 게이트로 승격 가능 |
