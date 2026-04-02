"""
IPO Report Generator — 모던 대시보드 스타일
A4 가로 인쇄용, DB 연동, Plotly 차트
사용법: python3 generate_report.py → ipo_report.html
"""

import sqlite3, json, os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipo_data.db")

# ── 컬러 팔레트 ──
C = {
    "primary": "#2563eb",    # blue-600
    "accent": "#f43f5e",     # rose-500
    "green": "#10b981",      # emerald-500
    "amber": "#f59e0b",      # amber-500
    "purple": "#8b5cf6",     # violet-500
    "slate": "#64748b",      # slate-500
    "gray": "#e2e8f0",       # slate-200
    "dark": "#1e293b",       # slate-800
    "bg": "#f8fafc",         # slate-50
    "bar1": "#3b82f6",       # blue-500
    "bar2": "#94a3b8",       # slate-400
    "line1": "#f43f5e",
    "line2": "#2563eb",
    "line3": "#10b981",
    "line4": "#8b5cf6",
    "line5": "#f59e0b",
}

# ── Plotly 공통 레이아웃 ──
def base_layout(title="", h=520, **kw):
    lo = {
        "height": h, "plot_bgcolor": "rgba(0,0,0,0)", "paper_bgcolor": "rgba(0,0,0,0)",
        "margin": {"t": 32, "b": 30, "l": 45, "r": 20},
        "font": {"family": "'Inter','Pretendard',sans-serif", "size": 11, "color": "#334155"},
        "xaxis": {"gridcolor": "rgba(0,0,0,0.05)", "linecolor": "#e2e8f0", "tickfont": {"size": 10}},
        "yaxis": {"gridcolor": "rgba(0,0,0,0.07)", "linecolor": "#e2e8f0", "tickfont": {"size": 10}, "zeroline": True, "zerolinecolor": "#cbd5e1"},
        "legend": {"orientation": "h", "y": 1.08, "font": {"size": 9.5}, "bgcolor": "rgba(0,0,0,0)"},
    }
    if title:
        lo["title"] = {"text": title, "font": {"size": 10.5, "color": "#334155", "family": "'Inter','Pretendard',sans-serif"}, "x": 0.01, "xanchor": "left"}
    lo.update(kw)
    return lo


def load_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM ipo_companies WHERE 처리상태='completed' AND 상장유형='신규상장' ORDER BY 상장일 DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def sa(values):
    v = [x for x in values if x is not None]
    return round(sum(v) / len(v), 1) if v else None


def band_ratio(d):
    lo, hi, p = d.get("공모가밴드_하단"), d.get("공모가밴드_상단"), d.get("확정공모가")
    if lo and hi and p and lo > 0 and hi > 0:
        return round((p / ((lo + hi) / 2) - 1) * 100, 1)
    return None


def generate():
    data = load_data()
    now = datetime.now().strftime("%Y.%m.%d")
    total = len(data)

    by_year = {}
    for d in data:
        yr = d["상장일"][:4] if d.get("상장일") else "?"
        by_year.setdefault(yr, []).append(d)

    Y5 = [str(y) for y in range(2021, 2026)]
    Y10 = [str(y) for y in range(2016, 2026)]

    pages = []

    def page2(title, headline, lc, rc, bullets, src="KIND · DART · 38커뮤니케이션"):
        pages.append({"title": title, "headline": headline, "charts": [lc, rc], "bullets": bullets, "source": src})

    def page1(title, headline, chart, bullets, src="KIND · DART · 38커뮤니케이션"):
        pages.append({"title": title, "headline": headline, "charts": [chart], "single": True, "bullets": bullets, "source": src})

    # ================================================================
    # 1. 상장건수 + 공모규모
    # ================================================================
    cnt_kd = [sum(1 for d in by_year.get(y, []) if d.get("시장구분") == "코스닥") for y in Y10]
    cnt_kp = [sum(1 for d in by_year.get(y, []) if d.get("시장구분") == "유가증권") for y in Y10]
    cnt_t = [a + b for a, b in zip(cnt_kd, cnt_kp)]
    y_max_cnt = max(max(cnt_kd), max(cnt_kp), max(cnt_t)) + 5

    # 코스피/코스닥 각각 평균공모금액 (억원)
    avg_kp = [round(sum(d["확정공모금액_억원"] for d in by_year.get(y, []) if d.get("확정공모금액_억원") and d.get("시장구분") == "유가증권") / max(sum(1 for d in by_year.get(y, []) if d.get("확정공모금액_억원") and d.get("시장구분") == "유가증권"), 1), 0) for y in Y10]
    avg_kd = [round(sum(d["확정공모금액_억원"] for d in by_year.get(y, []) if d.get("확정공모금액_억원") and d.get("시장구분") == "코스닥") / max(sum(1 for d in by_year.get(y, []) if d.get("확정공모금액_억원") and d.get("시장구분") == "코스닥"), 1), 0) for y in Y10]

    page2("대형딜 중심의 코스피 시장과, 기술상장 기업 중심의 코스닥 시장",
          f"10년간 신규상장 {total}건, 연평균 {total//10}건 · '21년 대형 IPO 집중",
          {"id": "p1a", "traces": json.dumps([
              {"x": Y10, "y": cnt_kp, "type": "bar", "name": "코스피", "marker": {"color": C["bar1"]},
               "text": [str(v) for v in cnt_kp], "textposition": "outside", "textfont": {"size": 9}},
              {"x": Y10, "y": avg_kp, "type": "scatter", "mode": "lines+markers", "name": "평균공모(억)", "yaxis": "y2",
               "line": {"color": C["accent"], "width": 2.5}, "marker": {"size": 6}},
          ]), "layout": json.dumps(base_layout("코스피 — 상장건수 · 평균공모규모",
              yaxis={"range": [0, y_max_cnt], "gridcolor": "rgba(0,0,0,0.07)", "linecolor": "#e2e8f0", "tickfont": {"size": 10}, "zeroline": True, "zerolinecolor": "#cbd5e1"},
              yaxis2={"title": "억원", "overlaying": "y", "side": "right", "gridcolor": "rgba(0,0,0,0)", "tickfont": {"size": 9}}))},
          {"id": "p1b", "traces": json.dumps([
              {"x": Y10, "y": cnt_kd, "type": "bar", "name": "코스닥", "marker": {"color": C["bar2"]},
               "text": [str(v) for v in cnt_kd], "textposition": "outside", "textfont": {"size": 9}},
              {"x": Y10, "y": avg_kd, "type": "scatter", "mode": "lines+markers", "name": "평균공모(억)", "yaxis": "y2",
               "line": {"color": C["accent"], "width": 2.5}, "marker": {"size": 6}},
          ]), "layout": json.dumps(base_layout("코스닥 — 상장건수 · 평균공모규모",
              yaxis={"range": [0, y_max_cnt], "gridcolor": "rgba(0,0,0,0.07)", "linecolor": "#e2e8f0", "tickfont": {"size": 10}, "zeroline": True, "zerolinecolor": "#cbd5e1"},
              yaxis2={"title": "억원", "overlaying": "y", "side": "right", "gridcolor": "rgba(0,0,0,0)", "tickfont": {"size": 9}}))},
          [f"'25년 76건, 전년 대비 소폭 감소 (YoY -5%)", f"'21년 공모규모 최대 — LG에너지솔루션(12.8조) 등 대형 IPO 집중", f"평균 공모규모는 연간 200~450억원 수준"])

    # ================================================================
    # 2. 상장트랙
    # ================================================================
    tracks = ["일반", "기술특례", "기술특례(성장성)", "이익미실현"]
    tc = [C["bar2"], C["accent"], C["amber"], C["green"]]
    td = {y: {t: sum(1 for d in by_year.get(y, []) if d.get("시장구분") == "코스닥" and d.get("상장트랙") == t) for t in tracks} for y in Y5}
    tr = [round((td[y].get("기술특례", 0) + td[y].get("기술특례(성장성)", 0) + td[y].get("이익미실현", 0)) / max(sum(td[y].values()), 1) * 100, 1) for y in Y5]

    page2("코스닥 상장트랙 현황 (2021~2025)",
          f"기술특례 비중 확대 추세 — '25년 {tr[-1]}%",
          {"id": "p2a", "traces": json.dumps([
              {"x": Y5, "y": [td[y][t] for y in Y5], "type": "bar", "name": t, "marker": {"color": tc[i]}}
              for i, t in enumerate(tracks)
          ]), "layout": json.dumps(base_layout("상장트랙별 건수", barmode="stack"))},
          {"id": "p2b", "traces": json.dumps([
              {"x": Y5, "y": tr, "type": "scatter", "mode": "lines+markers+text",
               "text": [f"{v}%" for v in tr], "textposition": "top center", "textfont": {"size": 10, "color": C["accent"]},
               "line": {"color": C["accent"], "width": 2.5}, "marker": {"size": 8, "color": C["accent"]}},
          ]), "layout": json.dumps(base_layout("기술특례 등 비중 (%)"))},
          ["'22년 이후 이익미실현기업 상장 제도 활성화, 매년 3~8건", "기술특례는 바이오·IT 중심, 일반상장 비중 감소 추세"])

    # ================================================================
    # 3. 산업별 히트맵
    # ================================================================
    secs = ["바이오/헬스케어", "IT/소프트웨어", "기계/장비", "반도체/디스플레이", "소비재/유통", "화학/소재", "2차전지/에너지", "엔터/미디어/게임", "자동차/모빌리티", "방산/우주항공", "금융", "건설/인프라"]
    sz = [[sum(1 for d in by_year.get(y, []) if d.get("산업분류") == s) for y in Y10] for s in secs]
    page1("산업별 상장 추이 (2016~2025)", "바이오·IT 중심 → 2차전지·방산으로 다변화",
          {"id": "p3", "traces": json.dumps([{
              "z": sz, "x": Y10, "y": secs, "type": "heatmap",
              "colorscale": [[0, "#f8fafc"], [0.2, "#dbeafe"], [0.4, "#93c5fd"], [0.7, "#3b82f6"], [1, "#1e40af"]],
              "text": [[str(v) if v else "" for v in r] for r in sz], "texttemplate": "%{text}",
              "textfont": {"size": 9}, "showscale": False,
          }]), "layout": json.dumps(base_layout(h=370, **{"margin": {"t": 10, "b": 25, "l": 125, "r": 10}}))},
          ["바이오/헬스케어 — 매년 최다 상장 섹터", "2차전지·방산 — '23년 이후 부상", "IT — '21년 피크 (크래프톤·카카오페이)"])

    # ================================================================
    # 4-1. 평가방법
    # ================================================================
    ms = ["PER", "EV/EBITDA", "PBR", "PSR"]
    mc = [C["bar2"], C["accent"], C["green"], C["purple"]]
    page1("밸류에이션 — 평가방법 (2021~2025)", "PER 80%+, EV/EBITDA는 대형 제조업 한정",
          {"id": "p4a", "traces": json.dumps([
              {"x": Y5, "y": [sum(1 for d in by_year.get(y, []) if d.get("평가방법") and m in d["평가방법"]) for y in Y5],
               "type": "bar", "name": m, "marker": {"color": mc[i]}}
              for i, m in enumerate(ms)
          ]), "layout": json.dumps(base_layout("평가방법 건수", barmode="stack"))},
          [f"PER 비율 {round(sum(1 for d in data if d.get('평가방법') and 'PER' in d['평가방법'])/total*100)}% — 코스닥 IPO 표준", "EV/EBITDA — LG에너지솔루션, HK이노엔 등"])

    # ================================================================
    # 4-2. 멀티플 + 할인율
    # ================================================================
    page2("밸류에이션 — 멀티플 · 할인율 (2021~2025)",
          f"PER 평균 {sa([d['적용멀티플'] for d in data if d.get('평가방법') and 'PER' in d['평가방법'] and d.get('적용멀티플') and d['상장일']>='2021'])}x, 할인율 25~40%",
          {"id": "p4b", "traces": json.dumps([
              {"x": Y5, "y": [sa([d["적용멀티플"] for d in by_year.get(y, []) if d.get("평가방법") and "PER" in d["평가방법"] and d.get("적용멀티플")]) for y in Y5],
               "type": "scatter", "mode": "lines+markers+text", "name": "PER 평균",
               "text": [str(sa([d["적용멀티플"] for d in by_year.get(y, []) if d.get("평가방법") and "PER" in d["평가방법"] and d.get("적용멀티플")])) for y in Y5],
               "textposition": "top center", "textfont": {"size": 9},
               "line": {"color": C["accent"], "width": 2.5}, "marker": {"size": 7, "color": C["accent"]}},
          ]), "layout": json.dumps(base_layout("PER 멀티플 추이 (배)"))},
          {"id": "p4c", "traces": json.dumps([
              {"x": Y5, "y": [sa([d["할인율_상단"] for d in by_year.get(y, []) if d.get("할인율_상단")]) for y in Y5],
               "type": "scatter", "mode": "lines+markers", "name": "상단", "line": {"color": C["accent"], "width": 2}},
              {"x": Y5, "y": [sa([d["할인율_하단"] for d in by_year.get(y, []) if d.get("할인율_하단")]) for y in Y5],
               "type": "scatter", "mode": "lines+markers", "name": "하단", "line": {"color": C["primary"], "width": 2}},
          ]), "layout": json.dumps(base_layout("할인율 밴드 추이 (%)"))},
          ["PER 20~25배 밴드 — 시장 상황에 따라 소폭 변동", "할인율 밴드 25~40% 수준 안정적 유지"])

    # ================================================================
    # 5. 수요예측/청약
    # ================================================================
    page2("수요예측 · 청약 현황 (2021~2025)", "참여기관수 1,500~2,000건 수준, 경쟁률은 시장 센티먼트 연동",
          {"id": "p5a", "traces": json.dumps([
              {"x": Y5, "y": [sa([d["수요예측_참여기관수"] for d in by_year.get(y, []) if d.get("수요예측_참여기관수")]) for y in Y5],
               "type": "bar", "name": "참여기관수", "marker": {"color": C["bar2"]},
               "text": [str(int(sa([d["수요예측_참여기관수"] for d in by_year.get(y, []) if d.get("수요예측_참여기관수")]) or 0)) for y in Y5],
               "textposition": "outside", "textfont": {"size": 9}},
          ]), "layout": json.dumps(base_layout("평균 참여기관수"))},
          {"id": "p5b", "traces": json.dumps([
              {"x": Y5, "y": [sa([d["기관경쟁률"] for d in by_year.get(y, []) if d.get("기관경쟁률")]) for y in Y5],
               "type": "scatter", "mode": "lines+markers", "name": "기관경쟁률",
               "line": {"color": C["accent"], "width": 2.5}, "marker": {"size": 6}},
              {"x": Y5, "y": [sa([d["청약경쟁률_비례"] for d in by_year.get(y, []) if d.get("청약경쟁률_비례")]) for y in Y5],
               "type": "scatter", "mode": "lines+markers", "name": "청약경쟁률",
               "line": {"color": C["primary"], "width": 2}},
          ]), "layout": json.dumps(base_layout("경쟁률 추이 (:1)"))},
          ["기관경쟁률 상승 = 시장 과열 시그널", "청약경쟁률은 기관경쟁률에 후행 연동"])

    # ================================================================
    # 6. 밴드 대비 확정가
    # ================================================================
    pr = [sa([band_ratio(d) for d in by_year.get(y, []) if band_ratio(d) is not None]) for y in Y5]
    page1("공모가 결정 — 밴드 대비 확정가 (2021~2025)", "확정공모가는 밴드 중간값 대비 평균 +5~15% 프리미엄",
          {"id": "p6", "traces": json.dumps([
              {"x": Y5, "y": pr, "type": "bar",
               "marker": {"color": [(C["accent"] if (v or 0) >= 0 else C["primary"]) for v in pr]},
               "text": [f"+{v}%" if v and v >= 0 else f"{v}%" for v in pr], "textposition": "outside", "textfont": {"size": 10}},
          ]), "layout": json.dumps(base_layout("밴드 중간값 대비 확정공모가 프리미엄 (%)"))},
          ["(+) = 밴드 상단 이상 확정 → 수요예측 흥행", "(-) = 밴드 하단 이하 → 시장 수요 부진"])

    # ================================================================
    # 7. 수익률 트렌드
    # ================================================================
    rc = [("상장일시가등락률", "시초가", C["accent"]), ("상장일종가등락률", "종가", C["primary"]),
          ("개월1_등락률", "1M", C["green"]), ("개월3_등락률", "3M", C["purple"]), ("개월6_등락률", "6M", C["amber"])]
    page1("상장 후 수익률 추이 (2021~2025)", "시초가 +50~80%, 시간 경과에 따라 수렴 — 1~3M이 실질 지표",
          {"id": "p7", "traces": json.dumps([
              {"x": Y5, "y": [sa([d[col] for d in by_year.get(y, []) if d.get(col)]) for y in Y5],
               "type": "scatter", "mode": "lines+markers", "name": lb, "line": {"color": cl, "width": 2}, "marker": {"size": 5}}
              for col, lb, cl in rc
          ]), "layout": json.dumps(base_layout("공모가 대비 수익률 (%)"))},
          ["시초가 수익률은 상한가(+300%) 포함, 평균값 왜곡 주의", "1~3개월 후 수익률이 실질적 투자성과 지표"])

    # ================================================================
    # 8-1~4. 산포도
    # ================================================================
    ss = [
        ("8-1", "수요예측 경쟁률 vs 확정공모가 프리미엄", "기관경쟁률(:1)", "프리미엄(%)", lambda d: d.get("기관경쟁률"), band_ratio, None),
        ("8-2", "수요예측 경쟁률 vs 청약경쟁률", "기관경쟁률(:1)", "청약경쟁률(:1)", lambda d: d.get("기관경쟁률"), lambda d: d.get("청약경쟁률_비례"), None),
        ("8-3", "수요예측 경쟁률 vs 수익률", "기관경쟁률(:1)", "수익률(%)", lambda d: d.get("기관경쟁률"), None,
         [("상장일시가등락률", "시초가", C["accent"]), ("상장일종가등락률", "종가", C["primary"]), ("개월1_등락률", "1M", C["green"])]),
        ("8-4", "청약경쟁률 vs 수익률", "청약경쟁률(:1)", "수익률(%)", lambda d: d.get("청약경쟁률_비례"), None,
         [("상장일시가등락률", "시초가", C["accent"]), ("상장일종가등락률", "종가", C["primary"]), ("개월1_등락률", "1M", C["green"])]),
    ]
    for num, st, xl, yl, xf, yf, multi in ss:
        if multi:
            tr = [{"x": [xf(d) for d in data if xf(d) and d.get(c)], "y": [d[c] for d in data if xf(d) and d.get(c)],
                   "mode": "markers", "type": "scatter", "name": lb, "marker": {"size": 4, "color": cl, "opacity": 0.35}}
                  for c, lb, cl in multi]
        else:
            fl = [d for d in data if xf(d) is not None and yf(d) is not None]
            tr = [{"x": [xf(d) for d in fl], "y": [yf(d) for d in fl], "text": [d["회사명"] for d in fl],
                   "mode": "markers", "type": "scatter", "marker": {"size": 4, "color": C["primary"], "opacity": 0.35}}]
        page1(f"상관관계 — {st}", st,
              {"id": f"p{num.replace('-','')}", "traces": json.dumps(tr),
               "layout": json.dumps(base_layout(h=370, **{"xaxis": {"title": xl, "gridcolor": "rgba(0,0,0,0.04)"},
                                                           "yaxis": {"title": yl, "gridcolor": "rgba(0,0,0,0.06)", "zeroline": True}}))}, [])

    # ================================================================
    # 9-1/9-2. 월별
    # ================================================================
    months = [f"{y}-{m:02d}" for y in range(2021, 2026) for m in range(1, 13)]
    for col, lb, pt in [(None, "프리미엄", "월별 공모가 프리미엄"), ("상장일종가등락률", "종가수익률", "월별 종가 수익률")]:
        mo = {}
        for d in data:
            if not d.get("상장일") or d["상장일"] < "2021": continue
            ym = d["상장일"][:7]
            v = d.get(col) if col else band_ratio(d)
            if v is not None: mo.setdefault(ym, []).append(v)
        ms2 = [m for m in months if m in mo]
        vs = [sa(mo[m]) for m in ms2]
        page1(f"{pt} (2021~2025)", f"월별 {lb} 추이",
              {"id": f"p9{'a' if not col else 'b'}", "traces": json.dumps([{
                  "x": ms2, "y": vs, "type": "bar",
                  "marker": {"color": [(C["accent"] if (v or 0) >= 0 else C["primary"]) for v in vs]},
              }]), "layout": json.dumps(base_layout(h=340, **{"xaxis": {"tickangle": -45, "dtick": 3, "tickfont": {"size": 7}}}))}, [])

    # ================================================================
    # 10 & 11. 유통비율/공모규모 vs 수익률
    # ================================================================
    for num, xc, xl in [("10", "유통가능주식수비율", "유통주식비율 (%)"), ("11", "확정공모금액_억원", "공모규모 (억원)")]:
        fl = [d for d in data if d.get(xc) and d.get("상장일종가등락률")]
        lt = "log" if xc == "확정공모금액_억원" else "linear"
        hl = "유통비율↓ = 수익률 분산↑" if num == "10" else "대형 IPO = 안정적 수익률"
        page1(f"{'유통비율' if num=='10' else '공모규모'} vs 종가수익률", hl,
              {"id": f"p{num}", "traces": json.dumps([{
                  "x": [d[xc] for d in fl], "y": [d["상장일종가등락률"] for d in fl], "text": [d["회사명"] for d in fl],
                  "mode": "markers", "type": "scatter", "marker": {"size": 5, "color": C["primary"], "opacity": 0.3},
              }]), "layout": json.dumps(base_layout(h=370, **{"xaxis": {"title": xl, "type": lt}}))}, [])

    # ================================================================
    # HTML
    # ================================================================
    ph = ""
    ps = ""
    for i, p in enumerate(pages):
        sg = p.get("single", False)
        ch = ""
        if sg:
            ch = f'<div id="{p["charts"][0]["id"]}" class="chart-full"></div>'
        else:
            ch = f'<div class="chart-grid"><div id="{p["charts"][0]["id"]}"></div><div id="{p["charts"][1]["id"]}"></div></div>'
        bh = "".join(f'<li>{b}</li>' for b in p.get("bullets", []) if b)
        ph += f'''
<div class="page">
  <div class="top-bar"><span class="label">IPO REPORT</span><span class="pg">{i+1} / {len(pages)}</span></div>
  <div class="title">{p["title"]}</div>
  <div class="headline">{p["headline"]}</div>
  <div class="charts">{ch}</div>
  {"<ul class='bullets'>" + bh + "</ul>" if bh else ""}
  <div class="footer"><span>{p.get("source","")}</span><span>{now}</span></div>
</div>
'''
        for c in p["charts"]:
            ps += f"Plotly.newPlot('{c['id']}',{c['traces']},{c['layout']},{{responsive:true,displayModeBar:false}});\n"

    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><title>IPO Report</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
@page {{ size: A4 landscape; margin: 0; }}
@media print {{
  .page {{ page-break-after: always; box-shadow: none !important; margin: 0 !important; }}
  .page:last-child {{ page-break-after: avoid; }}
  body {{ background: white; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: 'Inter','Pretendard',-apple-system,sans-serif; background: #e2e8f0; color: #1e293b; }}
.page {{
  width: 297mm; height: 210mm; background: white;
  margin: 6px auto; padding: 10mm 16mm 8mm;
  display: flex; flex-direction: column;
  box-shadow: 0 1px 3px rgba(0,0,0,.08);
  overflow: hidden; position: relative;
}}
.top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
.label {{ font-size: 0.55rem; font-weight: 600; letter-spacing: 2px; color: {C["primary"]}; text-transform: uppercase; }}
.pg {{ font-size: 0.55rem; color: #94a3b8; }}
.title {{ font-size: 0.75rem; font-weight: 500; color: #64748b; margin-bottom: 1px; }}
.headline {{
  font-size: 1rem; font-weight: 700; color: #0f172a;
  padding-bottom: 5px; margin-bottom: 5px;
  border-bottom: 2px solid {C["primary"]};
}}
.charts {{ flex: 1; overflow: hidden; min-height: 0; }}
.chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; height: 100%; }}
.chart-full {{ width: 100%; height: 100%; }}
.chart-grid > div {{ height: 100%; min-height: 0; }}
.bullets {{
  font-size: 0.7rem; color: #475569; padding: 5px 12px;
  background: #f8fafc; border-radius: 4px; margin-top: 4px;
  list-style: none;
}}
.bullets li {{ padding: 1px 0; }}
.bullets li::before {{ content: "→ "; color: {C["primary"]}; font-weight: 600; }}
.footer {{
  display: flex; justify-content: space-between;
  font-size: 0.5rem; color: #cbd5e1; margin-top: 4px;
  padding-top: 3px; border-top: 1px solid #f1f5f9;
}}
</style></head><body>
{ph}
<script>{ps}</script>
</body></html>"""

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipo_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"리포트 생성: {out} ({os.path.getsize(out)/1024:.0f}KB)")
    print(f"총 {len(pages)}페이지, {total}개 기업")


if __name__ == "__main__":
    generate()
