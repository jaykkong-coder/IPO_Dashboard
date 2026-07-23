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
