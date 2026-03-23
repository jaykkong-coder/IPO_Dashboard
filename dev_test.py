"""
파서 개발용 테스트 스크립트
- 파서 수정 후 빠르게 재파싱 + 검증
- 특정 회사만 테스트 가능

사용법:
  python3 dev_test.py              # 전체 재파싱 + 검증
  python3 dev_test.py 리브스메드     # 특정 회사만 테스트
  python3 dev_test.py --check      # 검증만 (재파싱 없이)
"""

import sys
import os
import sqlite3
import json
from ipo_extractor import extract_ipo_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DB_PATH = os.path.join(BASE_DIR, "ipo_data.db")

# 검증할 필드와 정상 범위
FIELD_RANGES = {
    "적용멀티플": (0.1, 200),
    "적용이익_백만원": (1, 10000000),
    "주당평가가액": (100, 1000000),
    "확정공모가": (1000, 500000),
    "상장후주식수": (100000, 500000000),
    "공모주식수": (1000, 500000000),
    "신주": (0, 500000000),
    "구주": (0, 500000000),
    "기준시가총액_억원": (1, 100000),
    "적정시가총액_억원": (1, 500000),
    "확정공모금액_억원": (1, 50000),
    "인수수수료총액_억원": (0.1, 100),
    "인수수수료율": (0.1, 10),
    "할인율_하단": (1, 80),
    "할인율_상단": (1, 80),
    "공모비율": (1, 50),
    "유통가능주식수비율": (1, 100),
}


def test_single(company_name):
    """특정 회사 1개 테스트"""
    doc_dir = os.path.join(DOCS_DIR, company_name)
    if not os.path.isdir(doc_dir):
        print(f"  {company_name}: docs 폴더 없음")
        return None

    fnames = [f for f in os.listdir(doc_dir) if f.endswith((".xml", ".html", ".htm"))]
    if not fnames:
        print(f"  {company_name}: 파싱 가능 파일 없음")
        return None

    filepath = os.path.join(doc_dir, fnames[0])
    data = extract_ipo_data(filepath)

    print(f"\n{'='*50}")
    print(f"  {company_name}")
    print(f"{'='*50}")

    # 주요 필드 출력
    fields = [
        ("평가방법", "평가모형"), ("적용멀티플", "적용멀티플"), ("적용이익", "적용이익_백만원"),
        ("적정시총", "적정시가총액_억원"), ("할인율", "할인율_하단"), ("확정공모가", "확정공모가"),
        ("주당평가가액", "주당평가가액"), ("공모주식수", "공모주식수"),
        ("신주", "신주"), ("구주", "구주"), ("상장후주식수", "상장후주식수"),
        ("기준시총", "기준시가총액_억원"), ("공모비율", "공모비율"),
        ("유통비율", "유통가능주식수비율"), ("인수수수료", "인수수수료총액_억원"),
        ("수수료율", "인수수수료율"), ("상장유형", "상장유형"),
    ]

    for label, key in fields:
        val = data.get(key)
        # 이상값 체크
        flag = ""
        if key in FIELD_RANGES and val is not None:
            lo, hi = FIELD_RANGES[key]
            if not (lo <= val <= hi):
                flag = " ❌ 이상값!"
        status = "✅" if val is not None else "  "
        if isinstance(val, float):
            print(f"  {status} {label:12s}: {val:>15,.1f}{flag}")
        elif isinstance(val, int):
            print(f"  {status} {label:12s}: {val:>15,}{flag}")
        else:
            print(f"  {status} {label:12s}: {val}{flag}")

    return data


def run_check():
    """DB 검증만 (재파싱 없이)"""
    if not os.path.exists(DB_PATH):
        print("DB 없음. 먼저 reparse.py를 실행하세요.")
        return

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 처리상태='completed'").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  추출률 ({total}건)")
    print(f"{'='*60}")

    all_fields = [
        "대표주관회사", "평가방법", "적용멀티플", "적용이익_백만원", "적정시가총액_억원",
        "할인율_하단", "확정공모가", "주당평가가액", "기준시가총액_억원", "확정공모금액_억원",
        "공모비율", "상장후주식수", "공모주식수", "신주", "유통가능주식수비율",
        "인수수수료총액_억원", "인수수수료율", "상장유형", "공모가최종",
    ]

    for f in all_fields:
        cnt = conn.execute(f"SELECT COUNT(*) FROM ipo_companies WHERE 처리상태='completed' AND {f} IS NOT NULL").fetchone()[0]
        pct = cnt / total * 100
        status = "✅" if pct >= 95 else "🔶" if pct >= 85 else "⚠️"
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {status} {f:25s} {bar} {cnt:2d}/{total} ({pct:.0f}%)")

    # 이상값 체크
    print(f"\n{'='*60}")
    print(f"  이상값 체크")
    print(f"{'='*60}")

    found_outlier = False
    for field, (lo, hi) in FIELD_RANGES.items():
        outliers = conn.execute(
            f"SELECT 회사명, {field} FROM ipo_companies WHERE 처리상태='completed' AND {field} IS NOT NULL AND ({field} < {lo} OR {field} > {hi})"
        ).fetchall()
        if outliers:
            found_outlier = True
            print(f"  ❌ {field}:")
            for name, val in outliers:
                print(f"     {name}: {val:,.1f}" if isinstance(val, float) else f"     {name}: {val:,}")

    if not found_outlier:
        print("  ✅ 이상값 없음")

    conn.close()


def run_full():
    """전체 재파싱 + 검증"""
    print("전체 재파싱 시작...")
    os.system(f"cd {BASE_DIR} && rm -f ipo_data.db && python3 reparse.py 2>&1 | tail -5")
    run_check()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--check":
            run_check()
        else:
            # 특정 회사 테스트
            test_single(arg)
    else:
        run_full()
