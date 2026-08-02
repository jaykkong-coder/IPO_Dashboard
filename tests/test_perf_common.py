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

def test_universe_sql_exposes_new_metrics():
    """유니버스에 실유통비율·배정기준확약률이 포함된다."""
    import perf_common as pc
    con = pc.get_db()
    rows = pc.load_universe(con)
    assert rows, "유니버스가 비어 있음"
    for key in ("free_float_pct", "lockup_inst_pct"):
        assert key in rows[0], f"missing {key}"

def test_ensure_tables_adds_lockup_total_to_existing_impl_reports():
    """열 추가는 기존 DB에도 반영돼야 한다.

    CREATE TABLE IF NOT EXISTS는 이미 있는 테이블의 스키마를 갱신하지 않는다.
    DDL만 고치고 끝내면 새 DB에서만 열이 생기고 실제 운영 DB에는 없어서,
    INSERT가 'no such column'으로 죽거나 값이 조용히 사라진다.
    """
    import sqlite3
    import perf_common as pc

    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE impl_reports(
        corp_code TEXT PRIMARY KEY, rcept_no TEXT, inst_alloc INTEGER,
        lockup_none INTEGER, parse_status TEXT)""")   # lockup_total 없는 구 스키마
    con.execute("INSERT INTO impl_reports(corp_code, parse_status) VALUES ('x','ok')")
    pc.ensure_tables(con)
    cols = {r[1] for r in con.execute("PRAGMA table_info(impl_reports)")}
    assert "lockup_total" in cols
    # 기존 행은 살아 있고 새 열은 NULL (= 재수집 대상 표식)
    assert list(con.execute(
        "SELECT corp_code, lockup_total FROM impl_reports")) == [("x", None)]
    pc.ensure_tables(con)                              # 두 번 돌려도 안전해야 한다
