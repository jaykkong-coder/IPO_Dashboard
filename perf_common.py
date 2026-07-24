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
  AND "확정공모가" IS NOT NULL
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
