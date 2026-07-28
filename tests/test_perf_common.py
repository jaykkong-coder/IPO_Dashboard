import perf_common as pc

def test_universe_size_and_fields():
    con = pc.get_db()
    uni = pc.load_universe(con)
    assert len(uni) >= 150                      # 2026-07 기준 172건 예상 (확정공모가 필터 적용 후)
    row = uni[0]
    for k in ("corp_code", "name", "listing_date", "market", "ipo_price", "industry"):
        assert k in row
    assert all(u["listing_date"] >= "2024-01-01" for u in uni)
    assert all("스팩" not in u["name"] for u in uni)
    assert all(u["ipo_price"] for u in uni)      # 이전상장(공모가 없음) 제외 확인

def test_corp_to_stock_map():
    m = pc.corp_to_stock_map()
    assert len(m) > 3000
    assert all(len(v) == 6 and v.isalnum() for v in list(m.values())[:100])

def test_ensure_tables():
    con = pc.get_db()
    pc.ensure_tables(con)
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"quarterly_earnings", "price_performance", "analysis_flags"} <= names

def test_ensure_tables_creates_share_structure():
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
