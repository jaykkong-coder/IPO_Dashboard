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
