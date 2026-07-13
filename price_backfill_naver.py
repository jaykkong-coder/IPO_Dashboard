"""
주가등락률 복구/백필 스크립트 (네이버 시세 기반)

배경: KIND 공모가대비주가추이 서비스가 2026-07 현재 월별(1M/3M/6M/1Y) 컬럼을
전부 0으로 반환한다 (서버측 이상). 이 스크립트는 KIND의 산정 규칙을 네이버
일별 시세로 재현해서 빈 값을 채운다.

KIND 산정 규칙 (파인메딕스/그래피/에스투더블유 9개 케이스로 역공학 검증):
  - 1M/3M/6M/1Y 주가 = 상장일 포함 20/60/120/240번째 거래일 종가
  - 등락률 = (해당일 종가 / 확정공모가 - 1) * 100

사용법:
  python3 price_backfill_naver.py            # NULL인 월별 필드만 채움
  python3 price_backfill_naver.py --restore-git  # 먼저 git HEAD DB에서 NULL 복원
"""
import os
import sys
import time
import json
import sqlite3
import subprocess
import requests
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ipo_data.db")

PRICE_FIELDS = [
    "상장일시가", "상장일시가등락률", "상장일종가", "상장일종가등락률",
    "개월1_주가", "개월1_등락률", "개월3_주가", "개월3_등락률",
    "개월6_주가", "개월6_등락률", "년1_주가", "년1_등락률",
]
# (컬럼 프리픽스, 상장일 포함 n번째 거래일)
HORIZONS = [("개월1", 20), ("개월3", 60), ("개월6", 120), ("년1", 240)]


def restore_from_git():
    """git HEAD에 커밋된 ipo_data.db에서, 현재 NULL인 주가 필드를 복원한다."""
    tmp = os.path.join(BASE_DIR, "_git_head_db.tmp")
    with open(tmp, "wb") as f:
        subprocess.run(["git", "-C", BASE_DIR, "show", "HEAD:ipo_data.db"], stdout=f, check=True)

    old = sqlite3.connect(tmp)
    old.row_factory = sqlite3.Row
    old_rows = {}
    for r in old.execute(f"SELECT 회사명, 상장일, {', '.join(PRICE_FIELDS)} FROM ipo_companies"):
        old_rows[(r["회사명"], r["상장일"])] = r
    old.close()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    restored = 0
    for r in conn.execute(f"SELECT id, 회사명, 상장일, {', '.join(PRICE_FIELDS)} FROM ipo_companies").fetchall():
        o = old_rows.get((r["회사명"], r["상장일"]))
        if not o:
            continue
        updates = {f: o[f] for f in PRICE_FIELDS if r[f] is None and o[f] is not None}
        if updates:
            conn.execute(
                f"UPDATE ipo_companies SET {', '.join(f'{k}=?' for k in updates)} WHERE id=?",
                list(updates.values()) + [r["id"]],
            )
            restored += 1
    conn.commit()
    conn.close()
    os.remove(tmp)
    print(f"[restore-git] {restored}건 행에서 NULL 필드 복원 완료")


def naver_series(symbol, start, end):
    """네이버 일별 시세: [(YYYYMMDD, 시가, 종가), ...] 날짜 오름차순"""
    url = (f"https://api.finance.naver.com/siseJson.naver?symbol={symbol}"
           f"&requestType=1&startTime={start}&endTime={end}&timeframe=day")
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    rows = json.loads(resp.text.replace("'", '"').strip())
    return [(str(x[0]), x[1], x[4]) for x in rows[1:]]  # 날짜, 시가, 종가


def load_ticker_map():
    """KIND 신규상장 목록에서 회사명 → 6자리 티커 매핑 (KIND 종목코드 + '0')"""
    from kind_scraper import get_kind_ipo_list
    m = {}
    for c in get_kind_ipo_list(start_date="2016-01-01"):
        code = c.get("종목코드")
        if code:
            m[c["회사명"]] = (str(code) + "0").zfill(6)
    return m


def backfill():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, 회사명, 상장일, 확정공모가,
               상장일시가, 상장일시가등락률, 상장일종가, 상장일종가등락률,
               개월1_주가, 개월3_주가, 개월6_주가, 년1_주가
        FROM ipo_companies
        WHERE 처리상태='completed' AND 상장일 IS NOT NULL AND 확정공모가 IS NOT NULL
          AND (개월1_주가 IS NULL OR 개월3_주가 IS NULL OR 개월6_주가 IS NULL OR 년1_주가 IS NULL
               OR 상장일시가 IS NULL)
        ORDER BY 상장일 DESC
    """).fetchall()
    print(f"[backfill] 대상: {len(rows)}건")

    tickers = load_ticker_map()
    today = date.today()
    filled, skipped = 0, 0

    for i, r in enumerate(rows):
        name, ld_s, ipo_price = r["회사명"], r["상장일"], r["확정공모가"]
        sym = tickers.get(name)
        if not sym:
            skipped += 1
            continue
        ld = date.fromisoformat(ld_s)
        # 최장 지평(240거래일 ≈ 350일) + 여유
        end = min(today, ld + timedelta(days=380))
        try:
            s = naver_series(sym, ld.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        except Exception:
            skipped += 1
            time.sleep(0.3)
            continue
        if not s or s[0][0] != ld.strftime("%Y%m%d"):
            # 상장일 시세가 없으면 (거래정지/상폐 등) 신뢰 불가 → 스킵
            skipped += 1
            time.sleep(0.2)
            continue

        updates = {}
        # 상장일 시가/종가
        if r["상장일시가"] is None and s[0][1]:
            updates["상장일시가"] = s[0][1]
            updates["상장일시가등락률"] = round((s[0][1] / ipo_price - 1) * 100, 1)
        if r["상장일종가"] is None and s[0][2]:
            updates["상장일종가"] = s[0][2]
            updates["상장일종가등락률"] = round((s[0][2] / ipo_price - 1) * 100, 1)
        # 월별 지평
        for prefix, nth in HORIZONS:
            if r[f"{prefix}_주가"] is None and len(s) >= nth:
                px = s[nth - 1][2]
                if px:
                    updates[f"{prefix}_주가"] = px
                    updates[f"{prefix}_등락률"] = round((px / ipo_price - 1) * 100, 1)

        if updates:
            conn.execute(
                f"UPDATE ipo_companies SET {', '.join(f'{k}=?' for k in updates)} WHERE id=?",
                list(updates.values()) + [r["id"]],
            )
            filled += 1
        if (i + 1) % 50 == 0:
            conn.commit()
            print(f"  진행: {i+1}/{len(rows)} (채움 {filled}, 스킵 {skipped})")
        time.sleep(0.25)

    conn.commit()
    conn.close()
    print(f"[backfill] 완료: {filled}건 채움, {skipped}건 스킵")


if __name__ == "__main__":
    if "--restore-git" in sys.argv:
        restore_from_git()
    backfill()
