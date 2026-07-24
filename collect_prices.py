"""pykrx로 지평별 공모가·시초가 대비 시장조정 수익률 계산 → price_performance.

시장조정 지수: pykrx 지수 API의 KRX 로그인 요구로 ETF 프록시 사용.
티커 매핑: CORPCODE.xml의 stock_code가 비어 있거나(신규상장 직후 등)
숫자 6자리가 아닌 경우, pykrx 전종목 이름 매칭으로 폴백한다.
"""
import argparse
import calendar
import datetime
import time

from pykrx import stock

import perf_common as pc

# 지수 API(get_index_ohlcv)는 KRX 로그인 요구로 깨져 있어 ETF로 대체.
# 069500=KODEX 200(코스피 프록시), 229200=KODEX 코스닥150(코스닥 프록시)
INDEX_CODE = {"유가증권": "069500", "코스피": "069500",
              "코스닥": "229200", "코스닥글로벌": "229200"}
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


def _slice_from(df, yyyymmdd: str):
    """ETF 전체 시계열 캐시에서 상장일 이후 구간만 슬라이스."""
    if df is None or df.empty:
        return df
    return df[df.index >= yyyymmdd]


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


def _dedupe_name_map(pairs) -> dict[str, str]:
    """(name, ticker) 페어를 name→ticker 맵으로 축약.

    동일 name이 서로 다른 ticker를 가리키면 모호하므로 제외한다
    (부분/추측 매칭보다 스킵이 낫다 — 오매칭이 더 위험).
    """
    out: dict[str, str] = {}
    ambiguous: set[str] = set()
    for name, ticker in pairs:
        if not name or name in ambiguous:
            continue
        if name in out and out[name] != ticker:
            ambiguous.add(name)
            del out[name]
            continue
        out[name] = ticker
    return out


def build_name_ticker_map() -> dict[str, str]:
    """pykrx 전종목(코스피/코스닥/코넥스) 이름→티커 맵을 1회 구축.

    stock.get_market_ticker_list()는 이 환경에서 전종목시세 엔드포인트가
    막혀 빈 응답을 반환하므로, get_market_ticker_name()이 내부적으로 쓰는
    상장종목검색 결과(StockTicker, 싱글턴 캐시)를 직접 사용한다.
    """
    try:
        from pykrx.website.krx.market.ticker import StockTicker
        df = StockTicker().listed
    except Exception as e:
        print(f"pykrx 이름맵 구축 실패, 폴백 비활성화: {e}")
        return {}
    return _dedupe_name_map(zip(df["종목"], df.index))


def resolve_ticker_by_name(name: str, name_map: dict[str, str]) -> str | None:
    """이름 기반 티커 조회: 정확일치 우선, 실패 시 공백 제거 후 일치. 그래도 실패하면 None."""
    if name in name_map:
        return name_map[name]
    stripped = _dedupe_name_map((n.replace(" ", ""), t) for n, t in name_map.items())
    return stripped.get(name.replace(" ", ""))


def main(limit=None):
    con = pc.get_db()
    pc.ensure_tables(con)
    tickers = pc.corp_to_stock_map()
    uni = pc.load_universe(con)[:limit]
    today = datetime.date.today().strftime("%Y%m%d")
    etf_cache: dict[str, object] = {}
    # ETF 캐시 시작일: 전체 유니버스의 최소 상장일부터 시작하여
    # 모든 종목에서 동일한 기준일부터 데이터를 보유하도록 보장
    min_listing_date = min(u["listing_date"] for u in uni).replace("-", "")
    name_map: dict[str, str] | None = None   # 이름→티커 폴백 맵 (지연 구축, 1회만)
    for i, u in enumerate(uni, 1):
        code = tickers.get(u["corp_code"])
        if not code:
            if name_map is None:
                name_map = build_name_ticker_map()
            code = resolve_ticker_by_name(u["name"], name_map)
            if code:
                print(f"{u['name']} → {code} (pykrx fallback)")
            else:
                print(f"[{i}] {u['name']}: 티커 없음 스킵")
                continue
        start = u["listing_date"].replace("-", "")
        px = stock.get_market_ohlcv(start, today, code)
        etf_code = INDEX_CODE.get(u["market"], "229200")
        if etf_code not in etf_cache:
            etf_cache[etf_code] = stock.get_market_ohlcv(min_listing_date, today, etf_code)
        idx = _slice_from(etf_cache[etf_code], start)
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
                     r["excess_return"], f"ETF:{etf_code}", r["price_date"]))
        con.commit()
        print(f"[{i}/{len(uni)}] {u['name']} ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    main(ap.parse_args().limit)
