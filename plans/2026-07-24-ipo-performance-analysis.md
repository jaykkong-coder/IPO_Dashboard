# IPO 주가 퍼포먼스 요인 분석 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2024년 이후 신규상장 ~186건을 시장조정 수익률로 W/M/L 그룹핑하고 실적·수급·업종·공모구조 변수로 대조 분석하는 재실행 가능 파이프라인 + JSON 산출.

**Architecture:** 기존 `ipo_data.db`(테이블 `ipo_companies`)에 테이블 3개를 추가하고, 수집 스크립트 2개(DART 분기실적, pykrx 수익률)와 분석 스크립트 1개가 순차 실행되어 `analysis_output.json`을 만든다. 보고서는 이 JSON을 근거로 ib-report 스킬이 작성한다.

**Tech Stack:** Python 3.12, sqlite3, requests(OpenDART REST), pykrx, pytest

## Global Constraints

- 프로젝트 루트: `/mnt/c/Users/kcci1/Projects/ipo-dashboard/` (모든 경로는 루트 기준 상대경로)
- DART API 키: `pipeline.py`의 `DART_API_KEY` 상수를 import해서 재사용 (키 하드코딩 금지)
- 분석 대상(유니버스): `상장일 >= '2024-01-01'` AND (`상장유형` IS NULL OR `상장유형` != 'SPAC')
- DB 컬럼명은 한글 — SQL에서 반드시 쌍따옴표로 감쌀 것 (예: `"상장일"`)
- DART 호출 간 `time.sleep(0.15)` (레이트리밋 예방), 일 한도 20,000콜
- 수익률 단위: % (소수 1자리 반올림). 금액 단위: 원(integer)
- 기존 파일 수정 금지: `pipeline.py`, `database.py`, `dashboard.py`는 읽기만
- 테스트: pytest. 네트워크 필요 테스트는 `@pytest.mark.network`로 표시하고 단일 종목 스모크만
- 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: 공통 모듈 perf_common.py (유니버스·티커 매핑·DB 스키마)

**Files:**
- Create: `perf_common.py`
- Create: `tests/test_perf_common.py`

**Interfaces:**
- Consumes: `ipo_data.db`의 `ipo_companies`, 루트의 `CORPCODE.xml`, `pipeline.DART_API_KEY`
- Produces (후속 태스크가 사용):
  - `get_db() -> sqlite3.Connection` (row_factory=sqlite3.Row)
  - `load_universe(con) -> list[dict]` — keys: `corp_code, name, listing_date, market, ipo_price, industry` (확정공모가 NULL이면 제외하지 않고 ipo_price=None)
  - `corp_to_stock_map() -> dict[str, str]` — corp_code → 6자리 종목코드 (CORPCODE.xml 파싱, stock_code 공백인 항목 제외)
  - `ensure_tables(con) -> None` — quarterly_earnings, price_performance, analysis_flags 생성 (IF NOT EXISTS)

- [ ] **Step 1: pytest 준비 확인**

Run: `cd /mnt/c/Users/kcci1/Projects/ipo-dashboard && python3 -m pytest --version || pip install pytest`
Expected: pytest 버전 출력 (없으면 설치 후 재확인)

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_perf_common.py`:
```python
import perf_common as pc

def test_universe_size_and_fields():
    con = pc.get_db()
    uni = pc.load_universe(con)
    assert len(uni) >= 150                      # 2026-07 기준 186건 예상
    row = uni[0]
    for k in ("corp_code", "name", "listing_date", "market", "ipo_price", "industry"):
        assert k in row
    assert all(u["listing_date"] >= "2024-01-01" for u in uni)
    assert all("스팩" not in u["name"] for u in uni)

def test_corp_to_stock_map():
    m = pc.corp_to_stock_map()
    assert len(m) > 3000
    assert all(len(v) == 6 and v.isdigit() for v in list(m.values())[:100])

def test_ensure_tables():
    con = pc.get_db()
    pc.ensure_tables(con)
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"quarterly_earnings", "price_performance", "analysis_flags"} <= names
```

- [ ] **Step 3: 실패 확인**

Run: `python3 -m pytest tests/test_perf_common.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'perf_common'`

- [ ] **Step 4: 구현**

`perf_common.py`:
```python
"""IPO 퍼포먼스 분석 공통 모듈: 유니버스 로드, 티커 매핑, 확장 테이블 스키마."""
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "ipo_data.db"
CORPCODE_XML = ROOT / "CORPCODE.xml"

UNIVERSE_SQL = """
SELECT dart_corp_code AS corp_code, "회사명" AS name, "상장일" AS listing_date,
       "시장구분" AS market, "확정공모가" AS ipo_price, "산업분류" AS industry,
       "상장일시가" AS open_price, "유통가능주식수비율" AS float_ratio,
       "기관경쟁률" AS inst_ratio, "의무보유확약비율" AS lockup_ratio,
       "적용이익_백만원" AS applied_profit_mm, "평가방법" AS valuation_method,
       "상단대비확정가비율" AS price_vs_band_top, "상장트랙" AS listing_track,
       "확정공모금액_억원" AS offer_size, "신주" AS new_shares, "구주" AS old_shares
FROM ipo_companies
WHERE "상장일" >= '2024-01-01'
  AND ("상장유형" IS NULL OR "상장유형" != 'SPAC')
ORDER BY "상장일"
"""


def get_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def load_universe(con) -> list[dict]:
    return [dict(r) for r in con.execute(UNIVERSE_SQL)]


def corp_to_stock_map() -> dict[str, str]:
    tree = ET.parse(CORPCODE_XML)
    out = {}
    for el in tree.getroot().iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if len(stock) == 6 and stock.isdigit():
            out[el.findtext("corp_code").strip()] = stock
    return out


DDL = [
    """CREATE TABLE IF NOT EXISTS quarterly_earnings(
        corp_code TEXT, quarter TEXT, fs_div TEXT,
        revenue INTEGER, op_income INTEGER, net_income INTEGER,
        is_cumulative INTEGER DEFAULT 0,
        PRIMARY KEY (corp_code, quarter))""",
    """CREATE TABLE IF NOT EXISTS price_performance(
        stock_code TEXT, horizon TEXT, base_price_type TEXT,
        abs_return REAL, excess_return REAL,
        index_used TEXT, price_date TEXT,
        PRIMARY KEY (stock_code, horizon, base_price_type))""",
    """CREATE TABLE IF NOT EXISTS analysis_flags(
        stock_code TEXT PRIMARY KEY, corp_code TEXT,
        group_6m TEXT, estimate_achievement REAL,
        earnings_shock INTEGER, industry_relative_6m REAL)""",
]


def ensure_tables(con) -> None:
    for ddl in DDL:
        con.execute(ddl)
    con.commit()
```

- [ ] **Step 5: 통과 확인**

Run: `python3 -m pytest tests/test_perf_common.py -v`
Expected: 3 passed

- [ ] **Step 6: 커밋**

```bash
git add perf_common.py tests/test_perf_common.py
git commit -m "feat: 퍼포먼스 분석 공통 모듈 (유니버스·티커맵·스키마)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: collect_quarterly.py (DART 분기실적 수집)

**Files:**
- Create: `collect_quarterly.py`
- Create: `tests/test_collect_quarterly.py`

**Interfaces:**
- Consumes: `perf_common.get_db/load_universe/ensure_tables`, `pipeline.DART_API_KEY`
- Produces:
  - `fetch_reports(corp_code, year) -> dict[str, dict]` — key `'Q1'|'H1'|'Q3'|'FY'`, value `{revenue, op_income, net_income, fs_div}` (누적값, 원 단위). 해당 보고서 없으면 key 부재
  - `to_quarters(reports_by_year: dict[int, dict]) -> list[dict]` — 분기 단독값 리스트 `{quarter:'YYYYQn', revenue, op_income, net_income, fs_div, is_cumulative}` (차감 불가 시 is_cumulative=1로 누적값 그대로 저장)
  - DB `quarterly_earnings` 채움. CLI: `python3 collect_quarterly.py [--limit N]`

**핵심 로직 (구현 지침):**
- OpenDART `https://opendart.fss.or.kr/api/fnlttSinglAcnt.json`, params: `crtfc_key, corp_code, bsns_year, reprt_code` (11013=1Q, 11012=반기, 11014=3Q, 11011=연간)
- 계정 매칭: `account_nm`이 `매출액`→revenue, `영업이익`→op_income, `당기순이익`→net_income (fs_div='CFS' 행 우선, 없으면 'OFS')
- `thstrm_amount`는 보고서 기간 누적으로 간주. 분기 단독값: Q1=Q1, Q2=H1−Q1, Q3=Q3−H1, Q4=FY−Q3. 직전 누적이 없으면 누적값을 저장하고 `is_cumulative=1`
- 수집 연도 범위: 상장연도−1 ~ 현재연도. status '013'(데이터 없음)은 정상 스킵
- 증분: 이미 저장된 (corp_code, quarter)는 재호출하지 않되, 각 기업의 최신 2개 분기는 항상 재조회(정정 반영)

- [ ] **Step 1: 실패하는 테스트 작성 (순수 로직 + 네트워크 스모크)**

`tests/test_collect_quarterly.py`:
```python
import pytest
import collect_quarterly as cq

def test_to_quarters_subtraction():
    reports = {2024: {
        "Q1": {"revenue": 100, "op_income": 10, "net_income": 8, "fs_div": "CFS"},
        "H1": {"revenue": 250, "op_income": 25, "net_income": 20, "fs_div": "CFS"},
        "Q3": {"revenue": 420, "op_income": 40, "net_income": 33, "fs_div": "CFS"},
        "FY": {"revenue": 600, "op_income": 55, "net_income": 45, "fs_div": "CFS"},
    }}
    qs = {q["quarter"]: q for q in cq.to_quarters(reports)}
    assert qs["2024Q2"]["revenue"] == 150
    assert qs["2024Q3"]["op_income"] == 15
    assert qs["2024Q4"]["net_income"] == 12
    assert all(q["is_cumulative"] == 0 for q in qs.values())

def test_to_quarters_missing_prior():
    reports = {2024: {"H1": {"revenue": 250, "op_income": 25,
                             "net_income": 20, "fs_div": "CFS"}}}
    qs = cq.to_quarters(reports)
    assert qs[0]["quarter"] == "2024Q2" and qs[0]["is_cumulative"] == 1

@pytest.mark.network
def test_fetch_reports_smoke():
    # 삼성전자 2024 연간: 매출 300조원 규모
    r = cq.fetch_reports("00126380", 2024)
    assert "FY" in r and r["FY"]["revenue"] > 2.9e14
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_collect_quarterly.py -v -m "not network"`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`collect_quarterly.py`:
```python
"""DART fnlttSinglAcnt로 유니버스 분기실적 수집 → quarterly_earnings."""
import argparse
import datetime
import time

import requests

import perf_common as pc
from pipeline import DART_API_KEY

URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
REPRT = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
ACCOUNTS = {"매출액": "revenue", "영업이익": "op_income", "당기순이익": "net_income"}
SEQ = ["Q1", "H1", "Q3", "FY"]          # 누적 차감 순서
QTR_NAME = {"Q1": "Q1", "H1": "Q2", "Q3": "Q3", "FY": "Q4"}


def _parse_amount(s):
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def fetch_reports(corp_code: str, year: int) -> dict:
    out = {}
    for key, code in REPRT.items():
        resp = requests.get(URL, params={
            "crtfc_key": DART_API_KEY, "corp_code": corp_code,
            "bsns_year": str(year), "reprt_code": code}, timeout=30)
        time.sleep(0.15)
        data = resp.json()
        if data.get("status") != "000":
            continue
        acc = {}
        for fs in ("CFS", "OFS"):
            rows = [r for r in data["list"] if r.get("fs_div") == fs]
            for r in rows:
                field = ACCOUNTS.get(r.get("account_nm", "").strip())
                if field and field not in acc:
                    v = _parse_amount(r.get("thstrm_amount"))
                    if v is not None:
                        acc[field] = v
                        acc.setdefault("fs_div", fs)
            if len(acc) > 1:            # fs_div + 1개 이상 잡히면 확정
                break
        if acc:
            out[key] = acc
    return out


def to_quarters(reports_by_year: dict) -> list[dict]:
    rows = []
    for year, reports in sorted(reports_by_year.items()):
        prev_cum = None                 # 직전 보고서 누적값
        for key in SEQ:
            cur = reports.get(key)
            if cur is None:
                prev_cum = None         # 연속성 끊김 → 이후 차감 불가
                continue
            row = {"quarter": f"{year}{QTR_NAME[key]}",
                   "fs_div": cur.get("fs_div", "CFS"), "is_cumulative": 0}
            for f in ("revenue", "op_income", "net_income"):
                if key == "Q1":
                    row[f] = cur.get(f)
                elif prev_cum is not None and cur.get(f) is not None \
                        and prev_cum.get(f) is not None:
                    row[f] = cur[f] - prev_cum[f]
                else:
                    row[f] = cur.get(f)
                    row["is_cumulative"] = 1
            rows.append(row)
            prev_cum = cur
    return rows


def main(limit=None):
    con = pc.get_db()
    pc.ensure_tables(con)
    uni = pc.load_universe(con)[:limit]
    today = datetime.date.today()
    for i, u in enumerate(uni, 1):
        corp, name = u["corp_code"], u["name"]
        start_year = int(u["listing_date"][:4]) - 1
        have = {r[0] for r in con.execute(
            "SELECT quarter FROM quarterly_earnings WHERE corp_code=?", (corp,))}
        latest2 = sorted(have)[-2:]     # 최신 2개 분기는 정정 반영 위해 재수집
        reports_by_year = {}
        for year in range(start_year, today.year + 1):
            year_quarters = {f"{year}Q{n}" for n in range(1, 5)}
            if year_quarters <= (have - set(latest2)):
                continue                # 증분: 완비된 과거 연도 스킵
            reports_by_year[year] = fetch_reports(corp, year)
        for q in to_quarters(reports_by_year):
            con.execute(
                """INSERT OR REPLACE INTO quarterly_earnings
                   (corp_code, quarter, fs_div, revenue, op_income,
                    net_income, is_cumulative) VALUES (?,?,?,?,?,?,?)""",
                (corp, q["quarter"], q["fs_div"], q["revenue"],
                 q["op_income"], q["net_income"], q["is_cumulative"]))
        con.commit()
        print(f"[{i}/{len(uni)}] {name} ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    main(ap.parse_args().limit)
```

- [ ] **Step 4: 오프라인 테스트 통과 확인**

Run: `python3 -m pytest tests/test_collect_quarterly.py -v -m "not network"`
Expected: 2 passed

- [ ] **Step 5: 네트워크 스모크 + 3사 시범 수집**

Run: `python3 -m pytest tests/test_collect_quarterly.py -v -m network`
Expected: 1 passed
Run: `python3 collect_quarterly.py --limit 3 && sqlite3 ipo_data.db "SELECT corp_code, quarter, revenue/100000000 FROM quarterly_earnings LIMIT 8"`
Expected: 3사 분기 행 출력, 매출이 억원 단위로 상식적 규모

- [ ] **Step 6: 커밋**

```bash
git add collect_quarterly.py tests/test_collect_quarterly.py
git commit -m "feat: DART 분기실적 수집기 (누적차감·증분수집)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: collect_prices.py (pykrx 수익률 계산)

**Files:**
- Create: `collect_prices.py`
- Create: `tests/test_collect_prices.py`

**Interfaces:**
- Consumes: `perf_common` (유니버스·티커맵·테이블), pykrx `stock.get_market_ohlcv`, `stock.get_index_ohlcv`
- Produces:
  - `horizon_dates(listing_date: str) -> dict[str, str]` — `{'1M': 'YYYYMMDD', '3M':…, '6M':…, '12M':…, 'NOW': 오늘}` (달력월 가산, 말일 보정, 미도래 지평은 key 제외)
  - `calc_returns(ohlcv_df, idx_df, base_price, listing_date, horizons) -> list[dict]` — `{horizon, abs_return, excess_return, price_date}` (기준일 이후 첫 거래일 종가 사용)
  - DB `price_performance` 채움 (base_price_type 'IPO'와 'OPEN' 각각). CLI: `python3 collect_prices.py [--limit N]`
- 지수 코드: 코스피 `1001`, 코스닥 `2001` (`get_index_ohlcv(start, end, code)`)
- 상장폐지·거래정지: OHLCV가 지평 기준일 이전에 끊기면 해당 지평 abs_return=NULL 저장 (row는 남김, price_date=마지막 거래일)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_collect_prices.py`:
```python
import pandas as pd
import pytest
import collect_prices as cp

def _df(dates, closes):
    return pd.DataFrame({"종가": closes},
                        index=pd.to_datetime(dates))

def test_horizon_dates_calendar_add():
    h = cp.horizon_dates("2025-01-31")
    assert h["1M"] == "20250228"          # 말일 보정
    assert h["6M"] == "20250731"
    assert "NOW" in h

def test_horizon_dates_skips_future():
    h = cp.horizon_dates("2026-07-01")    # 실행일 기준 12M 미도래
    assert "12M" not in h and "NOW" in h

def test_calc_returns_next_trading_day_and_excess():
    px = _df(["2024-01-02", "2024-02-05"], [12000, 15000])
    idx = _df(["2024-01-02", "2024-02-05"], [800.0, 840.0])
    out = cp.calc_returns(px, idx, base_price=10000,
                          listing_date="2024-01-02",
                          horizons={"1M": "20240202"})   # 2/2 휴장 → 2/5 종가
    r = out[0]
    assert r["abs_return"] == 50.0                       # 15000/10000-1
    assert r["excess_return"] == pytest.approx(45.0)     # 50% - 지수 5%
    assert r["price_date"] == "2024-02-05"

def test_calc_returns_delisted_null():
    px = _df(["2024-01-02"], [12000])                    # 이후 데이터 없음
    idx = _df(["2024-01-02", "2024-08-01"], [800.0, 900.0])
    out = cp.calc_returns(px, idx, 10000, "2024-01-02",
                          {"6M": "20240702"})
    assert out[0]["abs_return"] is None
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_collect_prices.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`collect_prices.py`:
```python
"""pykrx로 지평별 공모가·시초가 대비 시장조정 수익률 계산 → price_performance."""
import argparse
import calendar
import datetime
import time

from pykrx import stock

import perf_common as pc

INDEX_CODE = {"유가증권": "1001", "코스피": "1001",
              "코스닥": "2001", "코스닥글로벌": "2001"}
HORIZON_MONTHS = {"1M": 1, "3M": 3, "6M": 6, "12M": 12}


def _add_months(d: datetime.date, m: int) -> datetime.date:
    y, mo = divmod(d.month - 1 + m, 12)
    y, mo = d.year + y, mo + 1
    return datetime.date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def horizon_dates(listing_date: str) -> dict:
    base = datetime.date.fromisoformat(listing_date)
    today = datetime.date.today()
    out = {}
    for h, m in HORIZON_MONTHS.items():
        target = _add_months(base, m)
        if target <= today:
            out[h] = target.strftime("%Y%m%d")
    out["NOW"] = today.strftime("%Y%m%d")
    return out


def _close_on_or_after(df, yyyymmdd: str):
    """기준일 이후 첫 거래일 (날짜문자열, 종가). 없으면 (None, None)."""
    if df is None or df.empty:
        return None, None
    sub = df[df.index >= yyyymmdd]
    if sub.empty:
        return None, None
    ts = sub.index[0]
    return ts.strftime("%Y-%m-%d"), float(sub.iloc[0]["종가"])


def _close_on_or_before(df, yyyymmdd: str):
    sub = df[df.index <= yyyymmdd]
    if sub.empty:
        return None, None
    ts = sub.index[-1]
    return ts.strftime("%Y-%m-%d"), float(sub.iloc[-1]["종가"])


def calc_returns(px, idx, base_price, listing_date, horizons) -> list[dict]:
    ld = listing_date.replace("-", "")
    _, idx_base = _close_on_or_after(idx, ld)
    out = []
    for h, target in horizons.items():
        pdate, close = _close_on_or_after(px, target)
        if close is None:                      # 상장폐지 등 시계열 중단
            last_date, _ = _close_on_or_before(px, target)
            out.append({"horizon": h, "abs_return": None,
                        "excess_return": None, "price_date": last_date})
            continue
        abs_ret = round((close / base_price - 1) * 100, 1)
        _, idx_close = _close_on_or_after(idx, target)
        idx_ret = (idx_close / idx_base - 1) * 100 if idx_base and idx_close else 0.0
        out.append({"horizon": h, "abs_return": abs_ret,
                    "excess_return": round(abs_ret - idx_ret, 1),
                    "price_date": pdate})
    return out


def main(limit=None):
    con = pc.get_db()
    pc.ensure_tables(con)
    tickers = pc.corp_to_stock_map()
    uni = pc.load_universe(con)[:limit]
    today = datetime.date.today().strftime("%Y%m%d")
    for i, u in enumerate(uni, 1):
        code = tickers.get(u["corp_code"])
        if not code:
            print(f"[{i}] {u['name']}: 티커 없음 스킵")
            continue
        start = u["listing_date"].replace("-", "")
        px = stock.get_market_ohlcv(start, today, code)
        idx_code = INDEX_CODE.get(u["market"], "2001")
        idx = stock.get_index_ohlcv(start, today, idx_code)
        time.sleep(0.3)
        horizons = horizon_dates(u["listing_date"])
        for base_type, base in (("IPO", u["ipo_price"]), ("OPEN", u["open_price"])):
            if not base:
                continue
            for r in calc_returns(px, idx, base, u["listing_date"], horizons):
                con.execute(
                    """INSERT OR REPLACE INTO price_performance
                       (stock_code, horizon, base_price_type, abs_return,
                        excess_return, index_used, price_date)
                       VALUES (?,?,?,?,?,?,?)""",
                    (code, r["horizon"], base_type, r["abs_return"],
                     r["excess_return"], idx_code, r["price_date"]))
        con.commit()
        print(f"[{i}/{len(uni)}] {u['name']} ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    main(ap.parse_args().limit)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_collect_prices.py -v`
Expected: 4 passed

- [ ] **Step 5: 3사 시범 수집 및 육안 검증**

Run: `python3 collect_prices.py --limit 3 && sqlite3 ipo_data.db "SELECT * FROM price_performance LIMIT 10"`
Expected: IPO/OPEN × 지평별 행. abs_return이 DB의 기존 "개월6_등락률"과 근사한지 1개 종목 수동 대조 (±수%p 이내면 정상 — 기준일 처리 차이)

- [ ] **Step 6: 커밋**

```bash
git add collect_prices.py tests/test_collect_prices.py
git commit -m "feat: pykrx 지평별 시장조정 수익률 계산기

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 전량 수집 실행 (데이터 적재)

**Files:**
- Modify: 없음 (스크립트 실행만)

**Interfaces:**
- Consumes: Task 2·3의 CLI
- Produces: `quarterly_earnings`·`price_performance` 전량 적재 (후속 분석의 입력)

- [ ] **Step 1: 분기실적 전량 수집 (백그라운드, ~30분 예상)**

Run: `python3 collect_quarterly.py 2>&1 | tail -5` (run_in_background 권장)
Expected: `[186/186] … ok`

- [ ] **Step 2: 주가 전량 수집 (~15분 예상)**

Run: `python3 collect_prices.py 2>&1 | tail -5`
Expected: `[186/186] … ok` (티커 없음 스킵 5건 이하)

- [ ] **Step 3: 커버리지 검증 (성공 기준: 실적 90%+, 수익률 95%+)**

Run:
```bash
sqlite3 ipo_data.db "
SELECT (SELECT COUNT(DISTINCT corp_code) FROM quarterly_earnings) AS earn_corps,
       (SELECT COUNT(DISTINCT stock_code) FROM price_performance) AS px_corps;
SELECT horizon, COUNT(*) FROM price_performance
 WHERE base_price_type='IPO' AND abs_return IS NOT NULL GROUP BY horizon;"
```
Expected: earn_corps ≥ 167, px_corps ≥ 177. 미달 시 실패 종목 로그 확인 후 원인별 보완 (재실행으로 증분 수집됨)

- [ ] **Step 4: 커밋 (DB는 커밋하지 않음 — .gitignore 확인만)**

Run: `git status --short ipo_data.db` — 추적 중이면 그대로 두고(기존 정책 따름), untracked면 무시

---

### Task 5: analyze_performance.py (그룹핑·대조 통계·JSON 산출)

**Files:**
- Create: `analyze_performance.py`
- Create: `tests/test_analyze_performance.py`

**Interfaces:**
- Consumes: `perf_common`, `quarterly_earnings`, `price_performance`, `ipo_companies`
- Produces:
  - `tercile(values: list[float]) -> list[str]` — 각 원소에 'W'/'M'/'L' 부여 (상위⅓=W)
  - `estimate_achievement(applied_profit_mm, actual_net_by_year: dict[int,int], listing_year) -> float|None` — 상장 익년도 연간순이익(원) ÷ (적용이익 백만원×1e6) ×100. 적용이익 없거나 익년도 실적 없으면 None
  - `earnings_shock(quarters: list[dict], listing_date) -> int|None` — 상장 후 첫 2개 분기 중 op_income YoY −30% 이하 또는 (전년동기 흑자→적자) 있으면 1. YoY 비교쌍 없으면 None
  - `main()` → `analysis_flags` 채움 + `analysis_output.json` 저장
- `analysis_output.json` 구조 (ib-report가 소비):
```json
{
  "meta": {"asof": "YYYY-MM-DD", "universe_n": 186, "grouped_n": 166},
  "horizon_summary": {"1M": {"n":182, "median_abs":0.0, "median_excess":0.0}, "...":{}},
  "groups_6m": {"W": {"n":55, "median_excess":0.0}, "M": {}, "L": {}},
  "factor_contrast": [
    {"factor":"float_ratio","W_median":0.0,"L_median":0.0,"W_n":0,"L_n":0,
     "consistent_horizons":["1M","3M","6M"]}
  ],
  "industry_table": [{"industry":"반도체/디스플레이","n":12,"median_excess_6m":0.0,
                      "median_industry_relative":0.0}],
  "companies": [{"name":"","stock_code":"","industry":"","group_6m":"W",
                 "excess_6m":0.0,"float_ratio":0.0,"estimate_achievement":0.0,
                 "earnings_shock":0}]
}
```
- factor_contrast 대상 변수(각각 W vs L 중앙값): float_ratio, inst_ratio, lockup_ratio, offer_size, price_vs_band_top, 구주비중(old/(new+old)), estimate_achievement, earnings_shock 비율, 상장 후 2분기 매출 YoY 중앙값
- `consistent_horizons`: 해당 변수의 W>L(또는 W<L) 방향이 각 지평 tercile에서도 동일하게 나타나는 지평 목록

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_analyze_performance.py`:
```python
import analyze_performance as ap

def test_tercile_assignment():
    vals = [10, 20, 30, 40, 50, 60]
    groups = ap.tercile(vals)
    assert groups == ["L", "L", "M", "M", "W", "W"]

def test_estimate_achievement():
    # 적용이익 100억(백만원 단위 10000), 익년 실제 순이익 80억
    r = ap.estimate_achievement(10000, {2025: 8_000_000_000}, listing_year=2024)
    assert r == 80.0
    assert ap.estimate_achievement(None, {2025: 1}, 2024) is None
    assert ap.estimate_achievement(10000, {}, 2024) is None

def test_earnings_shock():
    qs = [
        {"quarter": "2023Q3", "op_income": 100},
        {"quarter": "2023Q4", "op_income": 100},
        {"quarter": "2024Q3", "op_income": 60},   # YoY -40% → 쇼크
        {"quarter": "2024Q4", "op_income": 110},
    ]
    assert ap.earnings_shock(qs, "2024-07-01") == 1
    qs2 = [{"quarter": "2023Q3", "op_income": 100},
           {"quarter": "2024Q3", "op_income": 90}]
    assert ap.earnings_shock(qs2, "2024-07-01") == 0
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_analyze_performance.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`analyze_performance.py` (핵심부 — 보조함수는 테스트를 통과하는 최소 구현):
```python
"""그룹핑·요인 대조 통계 → analysis_flags + analysis_output.json."""
import datetime
import json
import statistics

import perf_common as pc

SHOCK_THRESHOLD = -30.0          # 영업이익 YoY %


def tercile(values: list) -> list[str]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    n = len(values)
    cut_l, cut_w = n / 3, 2 * n / 3
    out = [""] * n
    for rank, i in enumerate(order):
        out[i] = "L" if rank < cut_l else ("W" if rank >= cut_w else "M")
    return out


def estimate_achievement(applied_profit_mm, actual_net_by_year, listing_year):
    if not applied_profit_mm:
        return None
    actual = actual_net_by_year.get(listing_year + 1)
    if actual is None:
        return None
    return round(actual / (applied_profit_mm * 1e6) * 100, 1)


def _prev_year_q(q):
    return f"{int(q[:4]) - 1}{q[4:]}"


def earnings_shock(quarters, listing_date):
    by_q = {q["quarter"]: q for q in quarters}
    listing_q = f"{listing_date[:4]}Q{(int(listing_date[5:7]) - 1) // 3 + 1}"
    after = sorted(q for q in by_q if q > listing_q)[:2]
    compared = 0
    for q in after:
        cur = by_q[q].get("op_income")
        prev = by_q.get(_prev_year_q(q), {}).get("op_income")
        if cur is None or prev is None or prev <= 0:
            continue
        compared += 1
        yoy = (cur / prev - 1) * 100
        if yoy <= SHOCK_THRESHOLD or cur < 0:
            return 1
    return 0 if compared else None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def main():
    con = pc.get_db()
    pc.ensure_tables(con)
    tickers = pc.corp_to_stock_map()
    uni = pc.load_universe(con)
    # --- 종목별 데이터 조립
    rows = []
    for u in uni:
        code = tickers.get(u["corp_code"])
        if not code:
            continue
        perf = {r["horizon"]: r["excess_return"] for r in con.execute(
            """SELECT horizon, excess_return FROM price_performance
               WHERE stock_code=? AND base_price_type='IPO'""", (code,))}
        quarters = [dict(r) for r in con.execute(
            """SELECT quarter, op_income, net_income, revenue, is_cumulative
               FROM quarterly_earnings WHERE corp_code=? ORDER BY quarter""",
            (u["corp_code"],))]
        net_by_year = {}
        for q in quarters:              # 연간 순이익 = 4분기 합 (완비 연도만)
            y = int(q["quarter"][:4])
            net_by_year.setdefault(y, []).append(q["net_income"])
        net_by_year = {y: sum(v) for y, v in net_by_year.items()
                       if len(v) == 4 and all(x is not None for x in v)}
        ly = int(u["listing_date"][:4])
        new_s, old_s = u["new_shares"] or 0, u["old_shares"] or 0
        rows.append({**u, "stock_code": code, "perf": perf,
                     "estimate_achievement": estimate_achievement(
                         u["applied_profit_mm"], net_by_year, ly),
                     "earnings_shock": earnings_shock(quarters, u["listing_date"]),
                     "old_share_ratio": round(old_s / (new_s + old_s) * 100, 1)
                     if (new_s + old_s) else None})
    # --- 지평별 tercile
    groups_by_h = {}
    for h in ("1M", "3M", "6M", "12M"):
        sub = [r for r in rows if r["perf"].get(h) is not None]
        labels = tercile([r["perf"][h] for r in sub])
        for r, g in zip(sub, labels):
            r.setdefault("groups", {})[h] = g
        groups_by_h[h] = sub
    # --- 업종 내 상대성과 (6M)
    by_ind = {}
    for r in groups_by_h["6M"]:
        by_ind.setdefault(r["industry"], []).append(r["perf"]["6M"])
    ind_median = {k: statistics.median(v) for k, v in by_ind.items()}
    for r in groups_by_h["6M"]:
        r["industry_relative_6m"] = round(
            r["perf"]["6M"] - ind_median[r["industry"]], 1)
    # --- analysis_flags 저장
    for r in rows:
        con.execute(
            """INSERT OR REPLACE INTO analysis_flags VALUES (?,?,?,?,?,?)""",
            (r["stock_code"], r["corp_code"], r.get("groups", {}).get("6M"),
             r["estimate_achievement"], r["earnings_shock"],
             r.get("industry_relative_6m")))
    con.commit()
    # --- factor_contrast
    factors = ["float_ratio", "inst_ratio", "lockup_ratio", "offer_size",
               "price_vs_band_top", "old_share_ratio",
               "estimate_achievement", "earnings_shock"]
    contrast = []
    six = groups_by_h["6M"]
    for f in factors:
        w = _median([r[f] for r in six if r["groups"]["6M"] == "W"])
        l = _median([r[f] for r in six if r["groups"]["6M"] == "L"])
        if w is None or l is None:
            continue
        direction = w > l
        consistent = []
        for h, sub in groups_by_h.items():
            wh = _median([r[f] for r in sub if r["groups"][h] == "W"])
            lh = _median([r[f] for r in sub if r["groups"][h] == "L"])
            if wh is not None and lh is not None and (wh > lh) == direction:
                consistent.append(h)
        contrast.append({"factor": f, "W_median": w, "L_median": l,
                         "W_n": sum(1 for r in six if r["groups"]["6M"] == "W"),
                         "L_n": sum(1 for r in six if r["groups"]["6M"] == "L"),
                         "consistent_horizons": consistent})
    # --- 산출
    out = {
        "meta": {"asof": datetime.date.today().isoformat(),
                 "universe_n": len(uni), "grouped_n": len(six)},
        "horizon_summary": {h: {"n": len(sub),
                                "median_excess": _median([r["perf"][h] for r in sub])}
                            for h, sub in groups_by_h.items()},
        "groups_6m": {g: {"n": sum(1 for r in six if r["groups"]["6M"] == g),
                          "median_excess": _median(
                              [r["perf"]["6M"] for r in six
                               if r["groups"]["6M"] == g])}
                      for g in ("W", "M", "L")},
        "factor_contrast": contrast,
        "industry_table": [
            {"industry": k, "n": len(v), "median_excess_6m": round(
                statistics.median(v), 1)}
            for k, v in sorted(by_ind.items(), key=lambda x: -len(x[1]))],
        "companies": [
            {"name": r["name"], "stock_code": r["stock_code"],
             "industry": r["industry"],
             "group_6m": r.get("groups", {}).get("6M"),
             "excess_6m": r["perf"].get("6M"),
             "float_ratio": r["float_ratio"],
             "estimate_achievement": r["estimate_achievement"],
             "earnings_shock": r["earnings_shock"]} for r in rows],
    }
    with open(pc.ROOT / "analysis_output.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"grouped {len(six)} / universe {len(uni)} → analysis_output.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_analyze_performance.py -v`
Expected: 3 passed

- [ ] **Step 5: 전량 분석 실행 + 산출물 검증**

Run: `python3 analyze_performance.py && python3 -m json.tool analysis_output.json | head -40`
Expected: `grouped 160+` 출력. JSON에서 groups_6m W/L의 median_excess 부호가 상식적(W 양수, L 음수)인지, factor_contrast에 8개 내외 변수가 있는지 확인

- [ ] **Step 6: 커밋**

```bash
git add analyze_performance.py tests/test_analyze_performance.py
git commit -m "feat: W/M/L 그룹핑·요인 대조 분석기 (analysis_output.json)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: ib-report 보고서 작성

**Files:**
- Create: `compare_report/ipo_performance_report.html` (ib-report 스킬 산출)
- Consumes: `analysis_output.json`

이 태스크는 코드가 아니라 보고서 작성이다. **반드시 `Skill(ib-report)`을 먼저 호출**해 템플릿 규칙(액션 타이틀, Key Insight 문체, 차트 색상 정책: 파랑>골드>회색)을 로드한 후 진행한다.

- [ ] **Step 1: `analysis_output.json` 전체 읽고 스토리라인 도출** — 지평 간 일관성 통과 요인(consistent_horizons가 3개 이상인 factor)을 확정 요인으로, 6M에서만 나타나는 요인은 참고로 분류
- [ ] **Step 2: ib-report 스킬 호출 후 A4 가로 보고서 작성** — 스펙 5.3 구성(총론 → W/L 프로파일 → 요인 딥다이브 4종 → 기간별 요인 전환 → 시사점). 데이터 수치는 JSON 값만 사용(임의 수치 금지)
- [ ] **Step 3: PDF 출력 확인** — 페이지 밀림·차트 해상도 점검 (til_20260326_ipo_report_v7 노하우 적용)
- [ ] **Step 4: 커밋**

```bash
git add compare_report/ipo_performance_report.html
git commit -m "docs: IPO 주가 퍼포먼스 요인 분석 보고서 v1

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review 결과

- 스펙 커버리지: §3(방법론)→Task 3·5, §4.2(수집)→Task 2·3·4, §4.3(파생)→Task 5, §5.3(보고서)→Task 6, §6(엣지: 상폐 NULL·차감불가 is_cumulative·비순이익 적용이익 None 처리) 반영. §6 "12월 결산 아닌 회사"는 저장 단계에서 자연 처리(reprt_code 그대로) — 보고서 각주로만 언급
- 타입 일관성: `load_universe` 반환 키를 Task 2·3·5가 동일하게 사용함을 확인 (`applied_profit_mm`, `float_ratio` 등)
- 성공 기준 검증 지점: Task 4 Step 3 (커버리지), Task 5 Step 5 (그룹 수·요인 수)
