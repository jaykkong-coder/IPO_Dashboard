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
