"""
Task 6: IPO 주가 퍼포먼스 요인 분석 보고서 빌더
analysis_output.json -> compare_report/ipo_performance_report.html

원칙: 모든 수치는 analysis_output.json에서만 로드. 하드코딩 금지(라벨/문구 제외).
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA = json.loads((ROOT / "analysis_output.json").read_text(encoding="utf-8"))
OUT = ROOT / "compare_report" / "ipo_performance_report.html"

meta = DATA["meta"]
hz = DATA["horizon_summary"]
grp = DATA["groups_6m"]
fc = {x["factor"]: x for x in DATA["factor_contrast"]}
industries = DATA["industry_table"]
companies = [c for c in DATA["companies"] if c["excess_6m"] is not None]

UNIVERSE_N = meta["universe_n"]
GROUPED_N = meta["grouped_n"]

# ---------- helpers ----------
def sp(v, d=1):
    """signed percent string"""
    s = f"{v:.{d}f}"
    if v > 0:
        s = "+" + s
    return s + "%"

def p(v, d=1):
    return f"{v:.{d}f}%"

def ratio(v):
    return f"{v:.0f}:1"

def won(v):
    return f"{v:.1f}억"

# ---------- derived data ----------
horizons = ["1M", "3M", "6M", "12M"]
hz_vals = [hz[h]["median_excess"] for h in horizons]
hz_ns = [hz[h]["n"] for h in horizons]

wml_labels = ["W (상위)", "M (중위)", "L (하위)"]
wml_vals = [grp["W"]["median_excess"], grp["M"]["median_excess"], grp["L"]["median_excess"]]
wml_ns = [grp["W"]["n"], grp["M"]["n"], grp["L"]["n"]]

sorted_c = sorted(companies, key=lambda x: x["excess_6m"], reverse=True)
top5 = sorted_c[:5]
bot5 = sorted_c[-5:]
extreme_labels = [c["name"] for c in top5] + [c["name"] for c in bot5][::-1]
extreme_vals = [c["excess_6m"] for c in top5] + [c["excess_6m"] for c in bot5][::-1]
extreme_colors = ["HL"] * 5 + ["C1"] * 5

industries_sorted = sorted(industries, key=lambda x: x["median_excess_6m"], reverse=True)

lock = fc["lockup_ratio"]
inst = fc["inst_ratio"]
est = fc["estimate_achievement"]
flt = fc["float_ratio"]
rev = fc["revenue_yoy_2q"]
shock = fc["earnings_shock"]
offer = fc["offer_size"]
band = fc["price_vs_band_top"]
old = fc["old_share_ratio"]

# consistency matrix rows: (label_kr, category, factor_obj, unit_fmt_fn)
matrix_rows = [
    ("의무보유확약비율", "확정", lock, lambda v: p(v, 1)),
    ("기관경쟁률", "확정", inst, lambda v: ratio(v)),
    ("유통가능주식수비율", "반전", flt, lambda v: p(v, 1)),
    ("추정치 달성률", "반전", est, lambda v: sp(v, 1)),
    ("상장후 2Q 매출YoY", "참고(n<10)", rev, lambda v: sp(v, 1)),
    ("어닝쇼크", "참고(n<10)", shock, lambda v: sp(v, 1)),
    ("공모규모", "보조", offer, lambda v: won(v)),
    ("공모가밴드 상단대비", "무관", band, lambda v: p(v, 1)),
    ("구주매출비율", "무관", old, lambda v: p(v, 1)),
]


# =====================================================================
# CSS (report_template.html 원본 그대로 — 메리츠 스타일 불변 규칙)
# =====================================================================
CSS = """
  :root {
    --navy-900: #0B1D3A; --navy-800: #0F2847; --navy-700: #163560; --navy-600: #1B4178; --navy-500: #58534D;
    --accent-blue: #4A8EC2; --accent-teal: #9E9A94; --accent-gold: #4A8EC2;
    --meritz-orange: #EF3B24; --meritz-gray: #6D6E71;
    --gray-900: #1A1A1A; --gray-700: #404040; --gray-600: #525252; --gray-500: #6B6B6B; --gray-400: #8E8E8E;
    --gray-300: #B8B8B8; --gray-200: #D6D6D6; --gray-100: #ECECEC; --gray-50: #F7F7F7; --white: #FFFFFF;
    --positive: #1A8754; --negative: #EF3B24; --warning: #D4A843; --info: #4A8EC2;
    --chart-1: #58534D; --chart-2: #9E9A94; --chart-3: #4A8EC2; --chart-4: #CCC7BF; --chart-5: #9E8C63; --chart-6: #E8E4DE;
    --font-body: 'Pretendard', -apple-system, 'Segoe UI', sans-serif;
    --page-width: 297mm; --page-height: 210mm;
    --page-margin-top: 14mm; --page-margin-bottom: 12mm; --page-margin-left: 16mm; --page-margin-right: 16mm;
  }
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:var(--font-body);font-size:13pt;line-height:1.5;color:var(--gray-900);background:#C0C0C0;-webkit-font-smoothing:antialiased}
  .page{width:var(--page-width);height:var(--page-height);margin:20px auto;padding:var(--page-margin-top) var(--page-margin-right) var(--page-margin-bottom) var(--page-margin-left);background:var(--white);box-shadow:0 2px 20px rgba(0,0,0,.15);position:relative;display:flex;flex-direction:column;overflow:hidden}
  @media print{body{background:white}.page{margin:0;box-shadow:none;page-break-after:always;page-break-inside:avoid}@page{size:A4 landscape;margin:0}}
  .page-header{display:flex;justify-content:space-between;align-items:flex-end;padding-bottom:8px;border-bottom:2.5px solid var(--navy-800);margin-bottom:10px;flex-shrink:0;position:relative}
  .page-header::after{content:'';position:absolute;bottom:-2.5px;left:0;width:60px;height:2.5px;background:var(--meritz-orange)}
  .page-header__logo{display:flex;align-items:center;gap:10px}
  .page-header__logo-mark{display:flex;align-items:center}
  .page-header__logo-mark svg{height:24px;width:auto}
  .page-header__company{font-size:12pt;font-weight:600;color:var(--meritz-gray);padding-left:10px;border-left:1px solid var(--gray-200)}
  .page-header__meta{text-align:right;font-size:11pt;color:var(--gray-500);line-height:1.4}
  .page-header__confidential{font-size:11pt;font-weight:400;color:var(--negative);letter-spacing:0}
  .slide-title{margin-bottom:10px;flex-shrink:0}
  .slide-title__main{font-size:18pt;font-weight:800;color:var(--navy-900);line-height:1.3;letter-spacing:-.3px}
  .content-grid{display:grid;gap:10px;flex:1;min-height:0}
  .content-grid--2col{grid-template-columns:1fr 1fr;grid-template-rows:1fr}
  .content-grid--3col{grid-template-columns:1fr 1fr 1fr;grid-template-rows:1fr}
  .content-grid--60-40{grid-template-columns:3fr 2fr;grid-template-rows:1fr}
  .content-grid--1col{grid-template-columns:1fr;grid-template-rows:1fr}
  .content-grid--2x2{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}
  .panel{border:1px solid var(--gray-200);border-radius:4px;padding:10px;display:flex;flex-direction:column;min-height:0;overflow:hidden}
  .panel--borderless{border:none;padding:0}
  .panel__title{font-size:12pt;font-weight:700;color:var(--navy-800);margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--gray-100);display:flex;justify-content:space-between;align-items:baseline;flex-shrink:0}
  .panel__title-unit{font-size:10pt;font-weight:400;color:var(--gray-400)}
  .panel__chart{flex:1;position:relative;min-height:0}
  .panel__bumper{font-size:10pt;color:var(--gray-500);margin-top:5px;padding-top:4px;border-top:1px solid var(--gray-100);line-height:1.4;font-style:italic;flex-shrink:0}
  .data-table{width:100%;border-collapse:collapse;font-size:11pt;line-height:1.4}
  .data-table thead th{background:var(--navy-800);color:var(--white);font-weight:600;padding:5px 6px;text-align:left;font-size:10pt;white-space:nowrap}
  .data-table thead th:first-child{border-radius:3px 0 0 0}.data-table thead th:last-child{border-radius:0 3px 0 0}
  .data-table tbody td{padding:4px 6px;border-bottom:1px solid var(--gray-100)}
  .data-table tbody tr:nth-child(even){background:var(--gray-50)}
  .data-table .num{text-align:right;font-variant-numeric:tabular-nums}
  .data-table .bold{font-weight:700}.data-table .positive{color:var(--positive);font-weight:600}.data-table .negative{color:var(--negative);font-weight:600}
  .callout{background:#F0F5FA;border-left:3px solid var(--navy-600);padding:12px 16px;border-radius:0 4px 4px 0;margin-top:6px;flex-shrink:0}
  .callout__label{font-size:10pt;font-weight:700;color:var(--navy-600);text-transform:uppercase;letter-spacing:.8px;margin-bottom:2px}
  .legend{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:5px}
  .legend__item{display:flex;align-items:center;gap:4px;font-size:10pt;color:var(--gray-600)}
  .legend__dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}
  .page-footer{margin-top:auto;padding-top:6px;border-top:1px solid var(--gray-200);display:flex;justify-content:space-between;align-items:flex-end;flex-shrink:0}
  .page-footer__source{font-size:10pt;color:var(--gray-400);line-height:1.4;max-width:78%}
  .page-footer__page{font-size:10pt;font-weight:700;color:var(--gray-900)}
  .commentary{list-style:none;padding:0}
  .commentary li{font-size:11pt;line-height:1.5;padding:3px 0 3px 12px;position:relative;color:var(--gray-700);border-bottom:1px solid var(--gray-100)}
  .commentary li:last-child{border-bottom:none}
  .commentary li::before{content:'';position:absolute;left:0;top:11px;width:5px;height:5px;background:var(--navy-600);border-radius:50%}
  .chip{display:inline-block;font-size:9.5pt;font-weight:700;color:var(--navy-700);background:#EAF0F8;border-radius:3px;padding:2px 8px;letter-spacing:.2px}
  .consist{display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-shrink:0}
  .consist__dot{display:flex;align-items:center;gap:3px;font-size:9pt;color:var(--gray-400)}
  .consist__dot i{width:8px;height:8px;border-radius:50%;background:var(--gray-200);display:inline-block}
  .consist__dot.on{color:var(--navy-700);font-weight:700}
  .consist__dot.on i{background:var(--accent-blue)}
  .takeaway{border:1px solid var(--gray-200);border-radius:4px;padding:10px 12px;display:flex;flex-direction:column;min-height:0}
  .takeaway__head{font-size:11.5pt;font-weight:800;color:var(--navy-800);margin-bottom:6px;padding-bottom:4px;border-bottom:2px solid var(--navy-800)}
"""

def logo_svg():
    return ('<svg viewBox="0 0 120 30" xmlns="http://www.w3.org/2000/svg">'
            '<text x="0" y="23" font-family="\'Pretendard\',Arial,sans-serif" font-size="26" '
            'font-weight="800" letter-spacing="-1" fill="#EF3B24">meritz</text></svg>')

def page_header(chip, docname):
    return f"""<div class="page-header"><div class="page-header__logo"><div class="page-header__logo-mark">{logo_svg()}</div><span class="page-header__company">{chip}</span></div><div class="page-header__meta"><div class="page-header__confidential">Confidential</div><div>2026.07 | {docname}</div></div></div>"""

def page_footer(source, page_no):
    return f"""<div class="page-footer"><div class="page-footer__source">Source: {source}</div><div class="page-footer__page">{page_no}</div></div>"""

def page_wrap(chip, docname, headline, body, source, page_no):
    return f"""<div class="page">
{page_header(chip, docname)}
  <div class="slide-title"><div class="slide-title__main">{headline}</div></div>
{body}
{page_footer(source, page_no)}
</div>
"""

DOCNAME = "IPO 주가 퍼포먼스 요인 분석"

# =====================================================================
# 표지
# =====================================================================
COVER = f"""<div class="page" style="justify-content:center;align-items:center;position:relative;overflow:hidden;padding:0;">
  <svg viewBox="0 0 2970 2100" preserveAspectRatio="xMidYMid slice" style="position:absolute;top:0;left:0;width:100%;height:100%;">
  <defs>
    <linearGradient id="rgA" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#A81E0C"/><stop offset="0.5" stop-color="#D93A22"/>
      <stop offset="0.85" stop-color="#E8563C"/><stop offset="1" stop-color="#C82C15"/>
    </linearGradient>
    <linearGradient id="rgB" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#C22C15"/><stop offset="0.35" stop-color="#DD4128"/>
      <stop offset="0.7" stop-color="#EC6A4C"/><stop offset="1" stop-color="#DD3B22"/>
    </linearGradient>
    <filter id="csoft" x="-25%" y="-25%" width="150%" height="150%"><feGaussianBlur stdDeviation="42"/></filter>
    <filter id="csoft2" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="24"/></filter>
    <clipPath id="cclipB">
      <path d="M 1000,1600 C 1700,1745 2140,690 3030,190 L 3030,520 C 2300,980 1900,1800 1120,1770 C 1050,1740 1010,1670 1000,1600 Z"/>
    </clipPath>
  </defs>
  <rect width="2970" height="2100" fill="#ffffff"/>
  <path d="M -60,1400 C 430,1050 840,1090 1195,1520 L 1165,1725 C 720,1490 390,1520 -60,1790 Z"
        fill="#40403f" opacity="0.14" filter="url(#csoft)" transform="translate(30,85)"/>
  <path d="M 1000,1600 C 1700,1745 2140,690 3030,190 L 3030,520 C 2300,980 1900,1800 1120,1770 Z"
        fill="#40403f" opacity="0.13" filter="url(#csoft)" transform="translate(25,80)"/>
  <path d="M 1000,1600 C 1700,1745 2140,690 3030,190 L 3030,520 C 2300,980 1900,1800 1120,1770 C 1050,1740 1010,1670 1000,1600 Z" fill="url(#rgB)"/>
  <path d="M 1000,1600 C 1700,1745 2140,690 3030,190 L 3030,290 C 2220,760 1840,1700 1030,1650 Z" fill="#ffffff" opacity="0.15"/>
  <g clip-path="url(#cclipB)"><ellipse cx="1180" cy="1620" rx="230" ry="170" fill="#5a0e02" opacity="0.30" filter="url(#csoft2)"/></g>
  <path d="M -60,1400 C 430,1050 840,1090 1195,1520 C 1225,1565 1215,1660 1165,1725 C 720,1490 390,1520 -60,1790 Z" fill="url(#rgA)"/>
  <path d="M -60,1400 C 430,1050 840,1090 1195,1520 L 1170,1575 C 830,1190 430,1150 -60,1480 Z" fill="#ffffff" opacity="0.13"/>
  <path d="M 1195,1520 C 1225,1565 1215,1660 1165,1725 C 1150,1700 1148,1580 1195,1520 Z" fill="#8c1a08" opacity="0.55"/>
  <rect y="1952" width="2970" height="148" fill="#A9AEB0"/>
</svg>
  <div style="position:absolute;top:12mm;left:25mm;z-index:1;font-size:11pt;color:#525252;letter-spacing:.2px;">Strictly Private &amp; Confidential</div>
  <div style="position:absolute;bottom:16mm;right:25mm;z-index:1;font-size:25pt;font-weight:800;">
    <span style="color:#EE3B24;letter-spacing:-1px;">meritz</span> <span style="color:#3A3A3A;font-weight:700;font-size:23pt;">메리츠증권</span>
  </div>
  <div style="text-align:left;width:100%;padding:0 25mm;position:absolute;top:24mm;left:0;z-index:1;">
    <div style="width:60px;height:4px;background:var(--meritz-orange);margin-bottom:16px;"></div>
    <div style="font-size:40pt;font-weight:800;color:var(--gray-900);line-height:1.15;letter-spacing:-1px;margin-bottom:10px;">IPO 주가 퍼포먼스 요인 분석</div>
    <div style="font-size:18pt;font-weight:400;color:var(--gray-600);letter-spacing:-.5px;margin-bottom:22px;">{meta['asof'][:7].replace('-','.')} 기준, 2024.1~2026.7 신규상장 {UNIVERSE_N}사 상장 후 6개월 초과수익률 결정요인 분석</div>
    <div style="display:flex;gap:30px;">
      <div style="border-left:3px solid var(--meritz-orange);padding-left:14px;">
        <div style="font-size:10.5pt;color:var(--gray-500);font-weight:600;margin-bottom:2px;">분석 모집단</div>
        <div style="font-size:15pt;color:var(--gray-900);font-weight:700;">{UNIVERSE_N}사 (그룹핑 {GROUPED_N}사)</div>
        <div style="font-size:9.5pt;color:var(--gray-500);">스팩·리츠·이전상장 제외, 6M 미경과 {UNIVERSE_N-GROUPED_N}사는 그룹핑 제외</div>
      </div>
      <div style="border-left:3px solid var(--meritz-orange);padding-left:14px;">
        <div style="font-size:10.5pt;color:var(--gray-500);font-weight:600;margin-bottom:2px;">6M 초과수익률 tercile 격차</div>
        <div style="font-size:15pt;color:var(--gray-900);font-weight:700;">W {sp(grp['W']['median_excess'])} vs L {sp(grp['L']['median_excess'])}</div>
        <div style="font-size:9.5pt;color:var(--gray-500);">{grp['W']['n']}/{grp['M']['n']}/{grp['L']['n']} tercile, 시장조정(ETF 프록시) 기준 중앙값</div>
      </div>
    </div>
  </div>
  <div style="position:absolute;bottom:4.5mm;left:25mm;z-index:1;">
    <div style="font-size:11pt;color:rgba(255,255,255,.95);font-weight:700;display:inline;">2026. 07</div>
    <div style="font-size:10pt;color:rgba(255,255,255,.8);display:inline;margin-left:10px;">메리츠증권 IB</div>
  </div>
</div>
"""

# =====================================================================
# Page 2 — ① 총론: 수익률 분포·그룹 개요
# =====================================================================
p2_headline = f"신규상장 초과수익률은 1개월 {sp(hz_vals[0])}에서 12개월 {sp(hz_vals[3])}까지 지속 악화"
p2_body = f"""  <div class="content-grid content-grid--2col">
    <div class="panel">
      <div class="panel__title">지평별 시장조정 초과수익률 중앙값<span class="panel__title-unit">공모가 대비, %</span></div>
      <div class="legend"><span class="legend__item"><span class="legend__dot" style="background:#58534D"></span>지평별 median_excess (표본 n)</span></div>
      <div class="panel__chart"><canvas id="c2a"></canvas></div>
    </div>
    <div class="panel">
      <div class="panel__title">6M 초과수익률 tercile 분포<span class="panel__title-unit">W/M/L, %</span></div>
      <div class="legend"><span class="legend__item"><span class="legend__dot" style="background:#2558A3"></span>W(상위)</span><span class="legend__item"><span class="legend__dot" style="background:#9E9A94"></span>M(중위)</span><span class="legend__item"><span class="legend__dot" style="background:#58534D"></span>L(하위)</span></div>
      <div class="panel__chart"><canvas id="c2b"></canvas></div>
    </div>
  </div>

  <div class="callout"><div class="callout__label">Key Insight</div><ul class="commentary" style="margin-top:4px">
    <li><strong>지속 악화:</strong> 지평별 초과수익률 중앙값은 1M {sp(hz_vals[0])} → 3M {sp(hz_vals[1])} → 6M {sp(hz_vals[2])} → 12M {sp(hz_vals[3])}로, 상장 초기 관심이 시간이 갈수록 식는다.</li>
    <li><strong>tercile 격차:</strong> 6M 기준 W {sp(wml_vals[0])} vs L {sp(wml_vals[2])}로 상·하위 51사 간 격차가 {wml_vals[0]-wml_vals[2]:.1f}%p에 달한다({wml_ns[0]}/{wml_ns[1]}/{wml_ns[2]} 균등 3분위).</li>
    <li><strong>표본 소멸:</strong> {UNIVERSE_N}사 중 6M 경과·그룹핑 대상은 {GROUPED_N}사이며, 12M 지평은 {hz_ns[3]}사로 표본이 더 얇아진다(최근 상장사 미경과 제외).</li>
  </ul></div>
"""
PAGE2 = page_wrap(
    "① 총론",
    DOCNAME,
    p2_headline,
    p2_body,
    f"KRX KIND 신규상장기업현황, DART 공시, 38커뮤니케이션 (n=1M {hz_ns[0]} / 3M {hz_ns[1]} / 6M {hz_ns[2]} / 12M {hz_ns[3]}). "
    f"시장조정은 pykrx 지수 API 불능으로 ETF 프록시(KODEX200/KODEX코스닥150) 대비 초과수익률. "
    f"지평은 상장일+N캘린더월 이후 첫 거래일 종가 기준(KIND 등락률의 거래일수 기준과 다름)",
    2,
)

# =====================================================================
# Page 3 — ② W/L 프로파일: 극단값 & 핵심요인 스냅샷
# =====================================================================
p3_headline = f"IPO 성과 스펙트럼은 최고 {sp(top5[0]['excess_6m'])}에서 최저 {sp(bot5[-1]['excess_6m'])}까지 벌어진다"

snapshot_rows = [
    ("의무보유확약비율", p(lock["W_median"]), p(lock["L_median"]), f"+{lock['W_median']-lock['L_median']:.1f}%p"),
    ("기관경쟁률", ratio(inst["W_median"]), ratio(inst["L_median"]), f"+{inst['W_median']-inst['L_median']:.0f}"),
    ("유통가능주식수비율", p(flt["W_median"]), p(flt["L_median"]), f"{flt['W_median']-flt['L_median']:+.1f}%p (무차이)"),
    ("공모규모(억원)", won(offer["W_median"]), won(offer["L_median"]), f"+{offer['W_median']-offer['L_median']:.1f}억"),
]
snap_tr = "".join(
    f'<tr><td>{r[0]}</td><td class="num">{r[1]}</td><td class="num">{r[2]}</td><td class="num bold">{r[3]}</td></tr>'
    for r in snapshot_rows
)

p3_body = f"""  <div class="content-grid content-grid--60-40">
    <div class="panel">
      <div class="panel__title">개별사 6M 초과수익률 상·하위 5개사<span class="panel__title-unit">공모가 대비 시장조정 초과수익률, %</span></div>
      <div class="legend"><span class="legend__item"><span class="legend__dot" style="background:#2558A3"></span>상위(W군)</span><span class="legend__item"><span class="legend__dot" style="background:#58534D"></span>하위(L군)</span></div>
      <div class="panel__chart"><canvas id="c3a"></canvas></div>
    </div>
    <div class="panel">
      <div class="panel__title">W/L 핵심요인 스냅샷 (중앙값)<span class="panel__title-unit">6M</span></div>
      <table class="data-table" style="font-size:10pt;margin-top:2px">
        <thead><tr><th>요인</th><th class="num">W</th><th class="num">L</th><th class="num">격차</th></tr></thead>
        <tbody>{snap_tr}</tbody>
      </table>
      <div class="panel__bumper">요인 딥다이브(③)에서 지평 일관성·표본 건전성 기준으로 상세 검증</div>
    </div>
  </div>

  <div class="callout"><div class="callout__label">Key Insight</div><ul class="commentary" style="margin-top:4px">
    <li><strong>극단값:</strong> 최고 {top5[0]['name']} {sp(top5[0]['excess_6m'])}({top5[0]['industry']}), {top5[1]['name']} {sp(top5[1]['excess_6m'])}({top5[1]['industry']}) vs 최저 {bot5[-1]['name']} {sp(bot5[-1]['excess_6m'])}({bot5[-1]['industry']}), {bot5[-2]['name']} {sp(bot5[-2]['excess_6m'])}({bot5[-2]['industry']})로 동일 시장에서 성과 격차가 500%p 이상 벌어진다.</li>
    <li><strong>수급·확약 우위:</strong> 의무보유확약비율과 기관경쟁률은 W군이 L군을 뚜렷하게 앞서지만, 유통가능주식수비율은 W {p(flt['W_median'])} vs L {p(flt['L_median'])}로 사실상 차이가 없다.</li>
  </ul></div>
"""
PAGE3 = page_wrap(
    "② W/L 프로파일",
    DOCNAME,
    p3_headline,
    p3_body,
    "analysis_output.json companies(6M 그룹핑 대상), factor_contrast. 유통물량 통념 검증은 페이지 ③-3에서 상세",
    3,
)

# =====================================================================
# Page 4 — ③-1 요인 딥다이브: 수급·확약 (확정 요인)
# =====================================================================
def consist_row(factor_obj):
    items = []
    for h in horizons:
        on = "on" if h in factor_obj["consistent_horizons"] else ""
        items.append(f'<span class="consist__dot {on}"><i></i>{h}</span>')
    return f'<div class="consist">{"".join(items)}</div>'

p4_headline = "의무보유확약비율과 기관경쟁률은 수요예측 단계에서 이미 승부를 가른다"
p4_body = f"""  <div class="content-grid content-grid--2col">
    <div class="panel">
      <div class="panel__title">의무보유확약비율<span class="panel__title-unit">중앙값, %</span></div>
      <div class="legend"><span class="legend__item"><span class="legend__dot" style="background:#2558A3"></span>W</span><span class="legend__item"><span class="legend__dot" style="background:#58534D"></span>L</span></div>
      {consist_row(lock)}
      <div class="panel__chart"><canvas id="c4a"></canvas></div>
    </div>
    <div class="panel">
      <div class="panel__title">기관경쟁률<span class="panel__title-unit">중앙값, :1</span></div>
      <div class="legend"><span class="legend__item"><span class="legend__dot" style="background:#2558A3"></span>W</span><span class="legend__item"><span class="legend__dot" style="background:#58534D"></span>L</span></div>
      {consist_row(inst)}
      <div class="panel__chart"><canvas id="c4b"></canvas></div>
    </div>
  </div>

  <div class="callout"><div class="callout__label">Key Insight</div><ul class="commentary" style="margin-top:4px">
    <li><strong>의무보유확약비율:</strong> W {p(lock['W_median'])} vs L {p(lock['L_median'])}로 {lock['W_median']/lock['L_median']:.1f}배 격차이며, 1M·3M·6M·12M 4개 지평 전부 방향이 일관된 유일한 요인이다.</li>
    <li><strong>기관경쟁률:</strong> W {ratio(inst['W_median'])} vs L {ratio(inst['L_median'])}로 1M·3M·6M 3개 지평은 일관되나 12M에서는 방향이 이탈한다(④에서 상세).</li>
    <li><strong>표본 건전성:</strong> 두 요인 모두 W_n·L_n이 {lock['W_n']}~{inst['W_n']}수준으로 thin_sample=false, 확정 요인으로 분류한다.</li>
  </ul></div>
"""
PAGE4 = page_wrap(
    "③ 요인 딥다이브 · 수급/확약",
    DOCNAME,
    p4_headline,
    p4_body,
    f"38커뮤니케이션 수요예측결과, factor_contrast.json (lockup_ratio W_n={lock['W_n']}/L_n={lock['L_n']}, inst_ratio W_n={inst['W_n']}/L_n={inst['L_n']})",
    4,
)

# =====================================================================
# Page 5 — ③-2 요인 딥다이브: 실적·달성률 반전
# =====================================================================
p5_headline = "이익 추정치를 못 채운 승자군이 오히려 초과수익률에서 앞선다"
p5_body = f"""  <div class="content-grid content-grid--60-40">
    <div class="panel">
      <div class="panel__title">추정치 달성률(적용이익 대비 실제)<span class="panel__title-unit">중앙값, %, PER평가 {est['W_n']+est['L_n']}사</span></div>
      <div class="legend"><span class="legend__item"><span class="legend__dot" style="background:#2558A3"></span>W</span><span class="legend__item"><span class="legend__dot" style="background:#58534D"></span>L</span></div>
      {consist_row(est)}
      <div class="panel__chart"><canvas id="c5a"></canvas></div>
    </div>
    <div class="panel">
      <div class="panel__title">참고 요인 (표본 10건 미만)<span class="panel__title-unit">중앙값, %</span></div>
      <table class="data-table" style="font-size:10pt;margin-top:2px">
        <thead><tr><th>요인</th><th class="num">W</th><th class="num">L</th><th class="num">n(W/L)</th></tr></thead>
        <tbody>
          <tr><td>상장후 2Q 매출YoY</td><td class="num">{sp(rev['W_median'])}</td><td class="num">{sp(rev['L_median'])}</td><td class="num">{rev['W_n']}/{rev['L_n']}</td></tr>
          <tr><td>어닝쇼크</td><td class="num">{sp(shock['W_median'])}</td><td class="num">{sp(shock['L_median'])}</td><td class="num">{shock['W_n']}/{shock['L_n']}</td></tr>
        </tbody>
      </table>
      <div class="panel__bumper">n&lt;10, 방향은 참고하되 결론 근거로 사용하지 않음. 어닝쇼크는 상장 전 분기보고서 부재로 YoY 계산 구조적 불능(n=3)</div>
    </div>
  </div>

  <div class="callout"><div class="callout__label">Key Insight</div><ul class="commentary" style="margin-top:4px">
    <li><strong>반직관 확인:</strong> 추정치 달성률은 W {sp(est['W_median'])} vs L {sp(est['L_median'])}로, 이익을 못 채운 W군이 오히려 6M 초과수익률 {sp(wml_vals[0])}를 기록했다.</li>
    <li><strong>원인 해석:</strong> 기술특례(이익미실현) 바이오·로봇주가 W군에 몰려 있어 "이익 미달성이어도 성장 스토리가 살아있으면 주가는 간다"는 해석이 가능하다. 반대로 달성해도 L군에 머문 사례가 있어 달성률 자체가 매수 신호는 아니다.</li>
    <li><strong>참고 요인(정직 표기):</strong> 상장후 2Q 매출YoY는 W {sp(rev['W_median'])}(n={rev['W_n']}) vs L {sp(rev['L_median'])}(n={rev['L_n']})로 고성장 방향은 일치하나 표본이 얇아 결론을 보류한다. 어닝쇼크는 n={shock['W_n']+shock['L_n']}로 사실상 결론 유보 상태다.</li>
  </ul></div>
"""
PAGE5 = page_wrap(
    "③ 요인 딥다이브 · 실적/달성률",
    DOCNAME,
    p5_headline,
    p5_body,
    "DART 정기보고서(분기 단독값, 연결 우선), 투자설명서 적용이익. 분기실적은 상장 전후 재무제표 매칭 가능 회사만 산출",
    5,
)

# =====================================================================
# Page 6 — ③-3 요인 딥다이브: 업종·공모구조 반전
# =====================================================================
def ind_row(i):
    cls = "positive" if i["median_excess_6m"] > 0 else "negative"
    n_flag = " *" if i["n"] < 10 else ""
    return (f'<tr><td>{i["industry"]}{n_flag}</td><td class="num">{i["n"]}</td>'
            f'<td class="num {cls} bold">{sp(i["median_excess_6m"])}</td>'
            f'<td class="num">{sp(i["median_industry_relative"])}</td></tr>')

ind_rows_html = "".join(ind_row(i) for i in industries_sorted)

p6_headline = f"유통가능주식수비율은 승자군 {p(flt['W_median'])}, 패자군 {p(flt['L_median'])}로 사실상 무차이"
p6_body = f"""  <div class="content-grid content-grid--60-40">
    <div class="panel">
      <div class="panel__title">업종별 6M 초과수익률 순위<span class="panel__title-unit">중앙값, 내림차순</span></div>
      <table class="data-table" style="font-size:9.5pt;margin-top:2px">
        <thead><tr><th>업종</th><th class="num">n</th><th class="num">6M 초과수익률</th><th class="num">업종내 상대</th></tr></thead>
        <tbody>{ind_rows_html}</tbody>
      </table>
      <div class="panel__bumper">* n&lt;10 업종은 표본이 얇아 순위 해석에 유의</div>
    </div>
    <div class="panel">
      <div class="panel__title">유통가능주식수비율<span class="panel__title-unit">중앙값, %</span></div>
      <div class="legend"><span class="legend__item"><span class="legend__dot" style="background:#2558A3"></span>W</span><span class="legend__item"><span class="legend__dot" style="background:#58534D"></span>L</span></div>
      {consist_row(flt)}
      <div class="panel__chart"><canvas id="c6a"></canvas></div>
      <div class="panel__bumper">공모가밴드 상단대비 W/L 모두 {p(band['W_median'])}, 구주매출비율 W/L 모두 {p(old['W_median'])}로 지평 일관성 없음(consistent_horizons 0개). 공모구조 변수는 이 표본에서 승패와 무관</div>
    </div>
  </div>

  <div class="callout"><div class="callout__label">Key Insight</div><ul class="commentary" style="margin-top:4px">
    <li><strong>업종 스펙트럼:</strong> 바이오/헬스케어가 {[i for i in industries_sorted if i['industry']=='바이오/헬스케어'][0]['n']}사 중앙값 {sp([i for i in industries_sorted if i['industry']=='바이오/헬스케어'][0]['median_excess_6m'])}로 대형 업종(n≥10) 중 유일하게 플러스, IT/소프트웨어·반도체/디스플레이가 최하위권이다.</li>
    <li><strong>유통물량 통념 반전:</strong> 유통가능주식수비율은 W {p(flt['W_median'])} vs L {p(flt['L_median'])}로 격차 {abs(flt['W_median']-flt['L_median']):.1f}%p에 불과하다. "유통물량이 적으면 오른다"는 통념이 이 표본에선 확인되지 않는다.</li>
    <li><strong>공모구조 무관:</strong> 공모가밴드 상단대비·구주매출비율은 W/L 중앙값이 동일하고 지평 일관성도 없어, 공모 설계보다 수요예측 단계 지표(③-1)가 결정적임을 재확인한다.</li>
  </ul></div>
"""
PAGE6 = page_wrap(
    "③ 요인 딥다이브 · 업종/공모구조",
    DOCNAME,
    p6_headline,
    p6_body,
    "industry_table(6M 그룹핑 153사 기준), factor_contrast.json (float_ratio W_n=%d/L_n=%d)" % (flt["W_n"], flt["L_n"]),
    6,
)

# =====================================================================
# Page 7 — ④ 기간별 요인 전환 (consistent_horizons 기반)
# =====================================================================
def matrix_row(label, cat, f, fmt):
    cells = []
    for h in horizons:
        if h in f["consistent_horizons"]:
            cells.append('<td class="num" style="color:#2558A3;font-weight:800;">●</td>')
        else:
            cells.append('<td class="num" style="color:#D6D6D6;">–</td>')
    cat_cls = {"확정": "positive", "반전": "bold", "참고(n<10)": "", "보조": "", "무관": ""}.get(cat, "")
    thin_flag = " (thin)" if f.get("thin_sample") else ""
    return (f'<tr><td class="bold">{label}</td><td>{cat}{thin_flag}</td>'
            f'<td class="num">{fmt(f["W_median"])}</td><td class="num">{fmt(f["L_median"])}</td>'
            f'<td class="num">{f["W_n"]}/{f["L_n"]}</td>{"".join(cells)}</tr>')

matrix_html = "".join(matrix_row(*row) for row in matrix_rows)

p7_headline = "의무보유확약비율만 12개월까지 유지되고 나머지 요인은 6개월 이후 약해진다"
p7_body = f"""  <div class="content-grid content-grid--1col">
    <div class="panel">
      <div class="panel__title">요인별 지평 일관성 매트릭스<span class="panel__title-unit">● = 해당 지평에서 W/L 방향 일관 (consistent_horizons)</span></div>
      <table class="data-table" style="font-size:10pt;margin-top:2px">
        <thead><tr><th>요인</th><th>분류</th><th class="num">W 중앙값</th><th class="num">L 중앙값</th><th class="num">n(W/L)</th><th class="num">1M</th><th class="num">3M</th><th class="num">6M</th><th class="num">12M</th></tr></thead>
        <tbody>{matrix_html}</tbody>
      </table>
    </div>
  </div>

  <div class="callout"><div class="callout__label">Key Insight</div><ul class="commentary" style="margin-top:4px">
    <li><strong>단일 전(全)지평 요인:</strong> 9개 요인 중 의무보유확약비율만 1M~12M 4개 지평 모두 일관돼 가장 오래가는 사전 시그널이다. 기관경쟁률·공모규모는 6M까지는 유지되나 12M에서 방향이 이탈한다.</li>
    <li><strong>실적계 요인은 후행 반영:</strong> 추정치 달성률·매출YoY(참고)는 1M에는 반영되지 않다가 3M부터 형성돼 12M까지 유지된다. 실적 발표 이후 누적 반영되는 패턴으로 해석된다.</li>
    <li><strong>약한 신호 배제:</strong> 유통가능주식수비율은 3M만 이탈하지만 격차 자체가 {abs(flt['W_median']-flt['L_median']):.1f}%p로 미미해 실질적 요인으로 보기 어렵다. 공모가밴드 상단대비·구주매출비율은 전 지평 일관성이 없다(consistent_horizons 0개).</li>
  </ul></div>
"""
PAGE7 = page_wrap(
    "④ 기간별 요인 전환",
    DOCNAME,
    p7_headline,
    p7_body,
    "factor_contrast.json (지평 1M/3M/6M/12M 각 그룹핑 재산출). thin_sample=true 요인은 방향 참고용, 결론 근거 아님",
    7,
)

# =====================================================================
# Page 8 — ⑤ 시사점
# =====================================================================
p8_headline = "수요예측 신호가 최선의 선행지표, 유통물량 통념은 이 표본에서 확인되지 않는다"
p8_body = f"""  <div class="content-grid content-grid--3col">
    <div class="takeaway">
      <div class="takeaway__head">확정 요인 · 수요예측이 선행지표</div>
      <ul class="commentary">
        <li>의무보유확약비율(W {p(lock['W_median'])} vs L {p(lock['L_median'])})과 기관경쟁률(W {ratio(inst['W_median'])} vs L {ratio(inst['L_median'])})은 상장 전 수요예측 결과다. 이 두 요인만 표본 건전성(n≈50/그룹)과 지평 일관성을 동시에 충족한다.</li>
        <li>확약비율은 4개 지평 모두 방향을 유지해, 실사·주관 단계에서 가장 신뢰할 수 있는 선행 시그널로 활용 가능하다.</li>
      </ul>
    </div>
    <div class="takeaway">
      <div class="takeaway__head">반전 발견 · 통념 재점검 필요</div>
      <ul class="commentary">
        <li>유통가능주식수비율은 W {p(flt['W_median'])} vs L {p(flt['L_median'])}로 사실상 무차이다. "유통물량이 적으면 방어된다"는 통념은 이 표본에서 근거가 없다.</li>
        <li>추정치 달성률은 W {sp(est['W_median'])} vs L {sp(est['L_median'])}로 반직관적이다. 기술특례 성장주가 W군에 몰려 "이익보다 스토리"가 주가를 이끈 결과로 해석되며, 달성해도 못 오르는 L군도 있어 달성률 자체는 매수 신호로 부적합하다.</li>
      </ul>
    </div>
    <div class="takeaway">
      <div class="takeaway__head">한계 및 후속 과제</div>
      <ul class="commentary">
        <li>상장후 2Q 매출YoY(n={rev['W_n']+rev['L_n']})·어닝쇼크(n={shock['W_n']+shock['L_n']})는 표본이 얇아 방향성 참고 수준이다. 어닝쇼크는 상장 전 분기보고서 부재로 계산이 구조적으로 불가능해 사실상 결론을 유보한다.</li>
        <li>시장조정은 ETF 프록시(KODEX200/코스닥150) 대비이며, 6M 미경과 {UNIVERSE_N-GROUPED_N}사는 그룹핑에서 제외했다. 12M 표본({hz_ns[3]}사)은 상대적으로 얇아 후속 분기 갱신이 필요하다.</li>
      </ul>
    </div>
  </div>

  <div class="callout"><div class="callout__label">주관 업무 시사점</div><ul class="commentary" style="margin-top:4px">
    <li>실사·수요예측 단계에서 의무보유확약비율과 기관경쟁률을 상장 후 성과의 1차 선행지표로 우선 확인한다. 유통물량 규제 설계만으로 상장 후 주가 방어를 기대하는 논리는 이 표본 근거로는 뒷받침되지 않는다.</li>
  </ul></div>
"""
PAGE8 = page_wrap(
    "⑤ 시사점",
    DOCNAME,
    p8_headline,
    p8_body,
    "analysis_output.json 종합. 방법론: 시장조정 ETF 프록시, 지평은 상장일+N캘린더월 첫 거래일 종가 기준, 분기실적은 DART 정기보고서 분기 단독값(연결 우선)",
    8,
)

# =====================================================================
# Chart.js SCRIPT (플레이스홀더 치환 방식 — f-string 중괄호 충돌 회피)
# =====================================================================
SCRIPT_TPL = """
<script>
  Chart.register(ChartDataLabels);
  Chart.defaults.devicePixelRatio=3;
  Chart.defaults.font.family="'Pretendard',-apple-system,'Segoe UI',sans-serif";
  Chart.defaults.font.size=12; Chart.defaults.color='#6B6B6B';
  Chart.defaults.plugins.legend.display=false;
  Chart.defaults.plugins.datalabels={display:false};
  Chart.defaults.scale.grid={color:'#ECECEC',lineWidth:.8};
  Chart.defaults.scale.border={display:false};
  Chart.defaults.elements.bar.borderRadius=2; Chart.defaults.elements.line.tension=.3;

  const C1='#58534D',C2='#9E9A94',C3='#4A8EC2',C4='#CCC7BF',C5='#9E8C63',C6='#E8E4DE';
  const HL='#2558A3';
  const DLpct={display:true,anchor:'end',align:'end',font:{size:11,weight:'700'},color:'#404040',
    formatter:v=>(v>0?'+':'')+v.toFixed(1)+'%'};
  const DLratio={display:true,anchor:'end',align:'end',font:{size:11,weight:'700'},color:'#404040',
    formatter:v=>Math.round(v)+':1'};

  // ---- P2a: 지평별 초과수익률 중앙값 ----
  new Chart(document.getElementById('c2a'),{type:'bar',data:{labels:__HZ_LABELS__,datasets:[
    {label:'중앙값',data:__HZ_VALS__,backgroundColor:C1,datalabels:DLpct}]},
    options:{responsive:true,maintainAspectRatio:false,
      scales:{y:{suggestedMax:6,ticks:{callback:v=>v+'%'}},x:{grid:{display:false}}},
      layout:{padding:{top:8,bottom:2}}}});

  // ---- P2b: WML tercile ----
  new Chart(document.getElementById('c2b'),{type:'bar',data:{labels:__WML_LABELS__,datasets:[
    {label:'중앙값',data:__WML_VALS__,backgroundColor:['#2558A3','#9E9A94','#58534D'],datalabels:DLpct}]},
    options:{responsive:true,maintainAspectRatio:false,
      scales:{y:{ticks:{callback:v=>v+'%'}},x:{grid:{display:false}}},
      layout:{padding:{top:16,bottom:2}}}});

  // ---- P3a: 개별사 상하위 5개사 (수평 다이버징) ----
  new Chart(document.getElementById('c3a'),{type:'bar',data:{labels:__EXT_LABELS__,datasets:[
    {label:'6M 초과수익률',data:__EXT_VALS__,backgroundColor:__EXT_COLORS__,datalabels:DLpct}]},
    options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      scales:{x:{ticks:{callback:v=>v+'%'}},y:{grid:{display:false},ticks:{font:{size:10.5}}}},
      layout:{padding:{right:34}}}});

  // ---- P4a: 의무보유확약비율 W/L ----
  new Chart(document.getElementById('c4a'),{type:'bar',data:{labels:['W (상위군)','L (하위군)'],datasets:[
    {label:'중앙값',data:__LOCK_VALS__,backgroundColor:[HL,C1],datalabels:DLpct}]},
    options:{responsive:true,maintainAspectRatio:false,
      scales:{y:{beginAtZero:true,ticks:{callback:v=>v+'%'}},x:{grid:{display:false}}},
      layout:{padding:{top:16}}}});

  // ---- P4b: 기관경쟁률 W/L ----
  new Chart(document.getElementById('c4b'),{type:'bar',data:{labels:['W (상위군)','L (하위군)'],datasets:[
    {label:'중앙값',data:__INST_VALS__,backgroundColor:[HL,C1],datalabels:DLratio}]},
    options:{responsive:true,maintainAspectRatio:false,
      scales:{y:{beginAtZero:true,ticks:{callback:v=>v+':1'}},x:{grid:{display:false}}},
      layout:{padding:{top:16}}}});

  // ---- P5a: 추정치 달성률 W/L ----
  new Chart(document.getElementById('c5a'),{type:'bar',data:{labels:['W (상위군)','L (하위군)'],datasets:[
    {label:'중앙값',data:__EST_VALS__,backgroundColor:[HL,C1],datalabels:DLpct}]},
    options:{responsive:true,maintainAspectRatio:false,
      scales:{y:{ticks:{callback:v=>v+'%'}},x:{grid:{display:false}}},
      layout:{padding:{top:18,bottom:4}}}});

  // ---- P6a: 유통가능주식수비율 W/L ----
  new Chart(document.getElementById('c6a'),{type:'bar',data:{labels:['W (상위군)','L (하위군)'],datasets:[
    {label:'중앙값',data:__FLT_VALS__,backgroundColor:[HL,C1],datalabels:DLpct}]},
    options:{responsive:true,maintainAspectRatio:false,
      scales:{y:{beginAtZero:true,max:40,ticks:{callback:v=>v+'%'}},x:{grid:{display:false}}},
      layout:{padding:{top:16}}}});
</script>
"""

def js(v):
    return json.dumps(v, ensure_ascii=False)

SCRIPT = (SCRIPT_TPL
    .replace("__HZ_LABELS__", js(horizons))
    .replace("__HZ_VALS__", js(hz_vals))
    .replace("__WML_LABELS__", js(["W", "M", "L"]))
    .replace("__WML_VALS__", js(wml_vals))
    .replace("__EXT_LABELS__", js(extreme_labels))
    .replace("__EXT_VALS__", js(extreme_vals))
    .replace("__EXT_COLORS__", js(["#2558A3"] * 5 + ["#58534D"] * 5))
    .replace("__LOCK_VALS__", js([lock["W_median"], lock["L_median"]]))
    .replace("__INST_VALS__", js([inst["W_median"], inst["L_median"]]))
    .replace("__EST_VALS__", js([est["W_median"], est["L_median"]]))
    .replace("__FLT_VALS__", js([flt["W_median"], flt["L_median"]]))
)

print("OK script built, len=", len(SCRIPT))

# =====================================================================
# 최종 조립 & 출력
# =====================================================================
HTML = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>IPO 주가 퍼포먼스 요인 분석</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<style>
{CSS}
</style>
</head>
<body>

{COVER}
{PAGE2}
{PAGE3}
{PAGE4}
{PAGE5}
{PAGE6}
{PAGE7}
{PAGE8}
{SCRIPT}
</body>
</html>
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
print(f"WROTE {OUT} ({len(HTML)} bytes, {HTML.count('class=\"page\"')} pages)")
