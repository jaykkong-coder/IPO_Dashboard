"""
ipo_dashboard.html 내장 데이터 갱신 스크립트

정적 대시보드는 DB를 JSON으로 내장하므로 DB 갱신 후 반드시 이 스크립트를 실행해야
대시보드에 반영된다. 갱신 대상:
  - D  : 개별 기업 레코드 (completed 전체 + SPAC)
  - Y  : 연도별 집계 (건수/멀티플/수익률/공모금액/기관경쟁률/트랙)
  - M  : 평가방법 분포
  - PP : 공모가 밴드 위치 분포
  - UW : 주관사 리그테이블 (상위 15)
  - 헤더 부제목 + KPI 카드 수치

주의: 2026-04 사고처럼 D만 갈아끼우면 뒤따르는 Y=..., 코드가 함께 잘려 대시보드가
통째로 깨진다. 반드시 이 스크립트로 갱신할 것 (json.JSONDecoder.raw_decode로
각 블록의 정확한 경계를 잡아 치환한다).

사용법: python3 update_dashboard_data.py
"""
import json
import os
import re
import sqlite3
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ipo_data.db")
HTML_PATH = os.path.join(BASE_DIR, "ipo_dashboard.html")

# 대시보드 표시명 → DB 컬럼명
FIELD_MAP = [
    ("회사명", "회사명"), ("상장일", "상장일"), ("시장", "시장구분"),
    ("상장트랙", "상장트랙"), ("산업분류", "산업분류"), ("주관사", "대표주관회사"),
    ("평가방법", "평가방법"), ("멀티플", "적용멀티플"), ("공모가", "확정공모가"),
    ("공모금액(억)", "확정공모금액_억원"), ("시총(억)", "기준시가총액_억원"),
    ("밴드(하)", "공모가밴드_하단"), ("밴드(상)", "공모가밴드_상단"),
    ("할인(하)", "할인율_하단"), ("할인(상)", "할인율_상단"),
    ("유통비율", "유통가능주식수비율"), ("기관경쟁", "기관경쟁률"),
    ("확약비율", "의무보유확약비율"), ("청약경쟁", "청약경쟁률_비례"),
    ("참여기관", "수요예측_참여기관수"), ("시가등락률", "상장일시가등락률"),
    ("종가등락률", "상장일종가등락률"), ("1개월", "개월1_등락률"),
    ("3개월", "개월3_등락률"), ("6개월", "개월6_등락률"), ("1년", "년1_등락률"),
]


def avg(vals, nd=1):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), nd) if v else None


def build_all():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # 모집단: completed 전체 + SPAC(스킵 포함) — v9 대시보드 기준. 코넥스 신규상장은 제외.
    pop = [dict(r) for r in conn.execute("""
        SELECT * FROM ipo_companies
        WHERE (처리상태='completed' OR (처리상태='skipped' AND 상장트랙='SPAC'))
          AND COALESCE(시장구분,'') != '코넥스'
        ORDER BY 상장일 DESC, 회사명
    """)]
    conn.close()

    D = [{disp: r[col] for disp, col in FIELD_MAP} for r in pop]

    years = sorted({(r["상장일"] or "")[:4] for r in pop if r["상장일"]})
    Y = {}
    for y in years:
        yr = [r for r in pop if (r["상장일"] or "")[:4] == y]
        Y[y] = {
            "count": len(yr),
            "avg_mult": avg([r["적용멀티플"] for r in yr]),
            "avg_return": avg([r["상장일종가등락률"] for r in yr]),  # 상장일 수익률(종가)
            "total_amt": round(sum(r["확정공모금액_억원"] or 0 for r in yr), 0),
            "avg_competition": avg([r["기관경쟁률"] for r in yr]),
            "track": dict(Counter(r["상장트랙"] for r in yr if r["상장트랙"])),
        }

    M = Counter()
    for r in pop:
        v = r["평가방법"] or ("SPAC" if r["상장트랙"] == "SPAC" else None)
        if v:
            M[v] += 1

    PP = Counter()
    for r in pop:
        lo, hi, p = r["공모가밴드_하단"], r["공모가밴드_상단"], r["확정공모가"]
        if not (lo and hi and p):
            PP["미분류"] += 1
        elif p > hi:
            PP["상단초과"] += 1
        elif p == hi:
            PP["상단"] += 1
        elif p == lo:
            PP["하단"] += 1
        elif p < lo:
            PP["하단미만"] += 1
        else:
            PP["밴드내"] += 1

    uw_cnt, uw_amt = Counter(), Counter()
    for r in pop:
        if not r["대표주관회사"]:
            continue
        for name in {x.strip() for x in r["대표주관회사"].split(",") if x.strip()}:
            uw_cnt[name] += 1
            uw_amt[name] += r["확정공모금액_억원"] or 0
    UW = [[k, {"count": uw_cnt[k], "total_amt": round(uw_amt[k], 2)}]
          for k in sorted(uw_cnt, key=lambda k: -uw_cnt[k])[:15]]

    return D, Y, dict(M), dict(PP), UW


def replace_block(html, anchor, new_json):
    """anchor('const D=' 등) 직후의 JSON 블록을 raw_decode 경계로 정확히 치환"""
    i = html.find(anchor)
    assert i >= 0, f"'{anchor}' 못 찾음"
    start = i + len(anchor)
    _, rel = json.JSONDecoder().raw_decode(html[start:])
    return html[:start] + new_json + html[start + rel:]


def js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def main():
    D, Y, M, PP, UW = build_all()
    html = open(HTML_PATH, encoding="utf-8").read()

    for anchor, obj in [("const D=", D), (",Y=", Y), (",M=", M), (",PP=", PP), (",UW=", UW)]:
        html = replace_block(html, anchor, js(obj))

    # 헤더 부제목 + KPI (전부 D에서 파생)
    n_spac = sum(1 for d in D if d["상장트랙"] == "SPAC")
    n_new = len(D) - n_spac
    n_special = sum(1 for d in D if d["상장트랙"] in ("기술특례", "기술특례(성장성)", "이익미실현"))
    kpis = {
        "신규상장": str(n_new),
        "SPAC": str(n_spac),
        "평균 멀티플": f"{avg([d['멀티플'] for d in D])}x",
        "상장일 수익률": f"{avg([d['종가등락률'] for d in D])}%",
        "기관경쟁률": f"{avg([d['기관경쟁'] for d in D], 0):.0f}:1",
        "기술특례 등": str(n_special),
        "전체": str(len(D)),
    }
    html = re.sub(r'(<p class="subtitle">)[^<]*(</p>)',
                  rf'\g<1>신규상장 {n_new} + SPAC {n_spac} = {len(D)}건 · 2016~2026\g<2>', html)
    for label, value in kpis.items():
        html = re.sub(
            rf'(<div class="kpi-value">)[^<]*(</div>\s*<div class="kpi-label">{re.escape(label)}</div>)',
            rf"\g<1>{value}\g<2>", html)

    open(HTML_PATH, "w", encoding="utf-8").write(html)
    dates = [d["상장일"] for d in D if d["상장일"]]
    print(f"갱신 완료: D {len(D)}건 (신규상장 {n_new} + SPAC {n_spac}), {min(dates)} ~ {max(dates)}")
    print(f"KPI: {kpis}")


if __name__ == "__main__":
    main()
