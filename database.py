"""
IPO Dashboard - SQLite DB
"""

import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipo_data.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """테이블 생성"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ipo_companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            회사명 TEXT NOT NULL,
            업종 TEXT,
            주요제품 TEXT,
            상장일 TEXT,
            결산월 TEXT,
            대표자 TEXT,
            지역 TEXT,
            시장구분 TEXT,
            -- DART 정보
            dart_corp_code TEXT,
            dart_rcept_no TEXT,
            -- 밸류에이션
            상장유형 TEXT,
            대표주관회사 TEXT,
            인수단 TEXT,
            평가방법 TEXT,
            적용멀티플 REAL,
            적용이익_백만원 REAL,
            적정시가총액_억원 REAL,
            할인율_하단 REAL,
            할인율_상단 REAL,
            공모가밴드_중간값 REAL,
            공모가밴드_하단 INTEGER,
            공모가밴드_상단 INTEGER,
            확정공모가 INTEGER,
            상단대비확정가비율 REAL,
            공모가최종 TEXT,
            기준시가총액_억원 REAL,
            확정공모금액_억원 REAL,
            주당평가가액 INTEGER,
            공모비율 REAL,
            상장후주식수 INTEGER,
            상장후주식수_희석포함 INTEGER,
            유통가능주식수 INTEGER,
            유통가능주식수비율 REAL,
            공모주식수 INTEGER,
            신주 INTEGER,
            구주 INTEGER,
            인수수수료총액_억원 REAL,
            인수수수료율 REAL,
            기관경쟁률 REAL,
            의무보유확약비율 REAL,
            청약경쟁률_비례 REAL,
            -- 주가 수익률 (KIND 공모가대비주가추이)
            상장일시가 INTEGER,
            상장일시가등락률 REAL,
            상장일종가 INTEGER,
            상장일종가등락률 REAL,
            개월1_주가 INTEGER,
            개월1_등락률 REAL,
            개월3_주가 INTEGER,
            개월3_등락률 REAL,
            개월6_주가 INTEGER,
            개월6_등락률 REAL,
            년1_주가 INTEGER,
            년1_등락률 REAL,
            -- 메타
            처리상태 TEXT DEFAULT 'pending',
            처리메모 TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(회사명, 상장일)
        );
    """)
    conn.commit()
    conn.close()


def upsert_company(data):
    """회사 데이터 upsert"""
    conn = get_conn()
    fields = [
        "회사명", "업종", "주요제품", "상장일", "결산월", "대표자", "지역", "시장구분",
        "dart_corp_code", "dart_rcept_no",
        "상장유형", "대표주관회사", "인수단", "평가방법",
        "적용멀티플", "적용이익_백만원", "적정시가총액_억원",
        "할인율_하단", "할인율_상단",
        "공모가밴드_중간값", "공모가밴드_하단", "공모가밴드_상단",
        "확정공모가", "상단대비확정가비율", "공모가최종",
        "기준시가총액_억원", "확정공모금액_억원",
        "주당평가가액", "공모비율",
        "상장후주식수", "상장후주식수_희석포함",
        "유통가능주식수", "유통가능주식수비율",
        "공모주식수", "신주", "구주",
        "인수수수료총액_억원",
        "인수수수료율",
        "기관경쟁률",
        "의무보유확약비율",
        "청약경쟁률_비례",
        "상장일시가", "상장일시가등락률",
        "상장일종가", "상장일종가등락률",
        "개월1_주가", "개월1_등락률",
        "개월3_주가", "개월3_등락률",
        "개월6_주가", "개월6_등락률",
        "년1_주가", "년1_등락률",
        "처리상태", "처리메모",
    ]

    values = {f: data.get(f) for f in fields}
    values["updated_at"] = "CURRENT_TIMESTAMP"

    # 평가방법 = 평가모형 우선 사용 (PER, PSR, EV/EBITDA 등 짧은 값)
    if "평가모형" in data and data["평가모형"]:
        values["평가방법"] = data["평가모형"]
    # 평가방법이 너무 긴 경우 정리
    if values.get("평가방법") and len(str(values["평가방법"])) > 30:
        text = str(values["평가방법"])
        if "PER" in text:
            values["평가방법"] = "PER"
        elif "PSR" in text:
            values["평가방법"] = "PSR"
        elif "EV/EBITDA" in text or "EV" in text:
            values["평가방법"] = "EV/EBITDA"
        elif "PBR" in text:
            values["평가방법"] = "PBR"
        else:
            values["평가방법"] = text[:20]

    cols = [f for f in fields if f in values]
    placeholders = ", ".join(["?" for _ in cols])
    update_clause = ", ".join([f"{c} = excluded.{c}" for c in cols if c != "회사명"])

    sql = f"""
        INSERT INTO ipo_companies ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(회사명, 상장일) DO UPDATE SET
        {update_clause},
        updated_at = CURRENT_TIMESTAMP
    """

    # SQLite INTEGER 범위 초과 방지: 큰 정수는 float으로 변환
    safe_values = []
    for c in cols:
        v = values[c]
        if isinstance(v, int) and (v > 2**62 or v < -(2**62)):
            v = float(v)
        safe_values.append(v)

    conn.execute(sql, safe_values)
    conn.commit()
    conn.close()


def get_all_companies():
    """전체 회사 목록 조회"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM ipo_companies ORDER BY 상장일 DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_companies():
    """미처리 회사 목록"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ipo_companies WHERE 처리상태 = 'pending' ORDER BY 상장일 DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_completed_companies():
    """처리 완료 회사 목록"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ipo_companies WHERE 처리상태 = 'completed' ORDER BY 상장일 DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    """처리 현황 통계"""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM ipo_companies").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 처리상태 = 'completed'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 처리상태 = 'failed'").fetchone()[0]
    skipped = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 처리상태 = 'skipped'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 처리상태 = 'pending'").fetchone()[0]
    conn.close()
    return {"total": total, "completed": completed, "failed": failed, "skipped": skipped, "pending": pending}


if __name__ == "__main__":
    init_db()
    print(f"DB 초기화 완료: {DB_PATH}")
    stats = get_stats()
    print(f"현황: {stats}")
