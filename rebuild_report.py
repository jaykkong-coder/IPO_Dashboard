#!/usr/bin/env python3
"""ipo_report.html 재생성 스크립트 - 전체 리뷰 반영"""

import json

# SD 데이터 로드
with open('/tmp/sd_data.txt', 'r') as f:
    sd_data = f.read()

html = '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IPO 시장 분석 리포트 (2016-2025)</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<style>
  :root {
    --navy-900: #0B1D3A; --navy-800: #0F2847; --navy-700: #163560; --navy-600: #1B4178; --navy-500: #2558A3;
    --accent-blue: #3B82C4; --accent-teal: #2BA5A5; --accent-gold: #D4A843;
    --meritz-orange: #EF3B24; --meritz-gray: #6D6E71;
    --gray-900: #1A1A1A; --gray-700: #404040; --gray-600: #525252; --gray-500: #6B6B6B; --gray-400: #8E8E8E;
    --gray-300: #B8B8B8; --gray-200: #D6D6D6; --gray-100: #ECECEC; --gray-50: #F7F7F7; --white: #FFFFFF;
    --positive: #1A8754; --negative: #C53030; --warning: #D4A843; --info: #3B82C4;
    --chart-1: #2558A3; --chart-2: #2BA5A5; --chart-3: #D4A843; --chart-4: #7B61A6; --chart-5: #C53030; --chart-6: #8E8E8E;
    --font-body: 'Pretendard', -apple-system, 'Segoe UI', sans-serif;
    --page-width: 297mm; --page-height: 210mm;
    --page-margin-top: 14mm; --page-margin-bottom: 12mm; --page-margin-left: 16mm; --page-margin-right: 16mm;
  }
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:var(--font-body);font-size:10pt;line-height:1.5;color:var(--gray-900);background:#C0C0C0;-webkit-font-smoothing:antialiased}
  .page{width:var(--page-width);min-height:var(--page-height);margin:20px auto;padding:var(--page-margin-top) var(--page-margin-right) var(--page-margin-bottom) var(--page-margin-left);background:var(--white);box-shadow:0 2px 20px rgba(0,0,0,.15);position:relative;display:flex;flex-direction:column;overflow:hidden}
  @media print{body{background:white}.page{margin:0;box-shadow:none;page-break-after:always}@page{size:A4 landscape;margin:0}}
  .page-header{display:flex;justify-content:space-between;align-items:flex-end;padding-bottom:8px;border-bottom:2.5px solid var(--navy-800);margin-bottom:12px;flex-shrink:0;position:relative}
  .page-header::after{content:'';position:absolute;bottom:-2.5px;left:0;width:60px;height:2.5px;background:var(--meritz-orange)}
  .page-header__logo{display:flex;align-items:center;gap:10px}
  .page-header__logo-mark{display:flex;align-items:center}
  .page-header__logo-mark svg{height:18px;width:auto}
  .page-header__company{font-size:9.5pt;font-weight:600;color:var(--meritz-gray);padding-left:10px;border-left:1px solid var(--gray-200)}
  .page-header__meta{text-align:right;font-size:8.5pt;color:var(--gray-500);line-height:1.4}
  .page-header__confidential{font-size:7.5pt;font-weight:600;color:var(--negative);text-transform:uppercase;letter-spacing:1px}
  .slide-title{margin-bottom:10px;flex-shrink:0}
  .slide-title__main{font-size:14.5pt;font-weight:800;color:var(--navy-900);line-height:1.3;letter-spacing:-.3px;margin-bottom:2px}
  .slide-title__sub{font-size:9.5pt;color:var(--gray-500);font-weight:400}
  .kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px;flex-shrink:0}
  .kpi-row--5{grid-template-columns:repeat(5,1fr)}
  .kpi-card{background:var(--gray-50);border:1px solid var(--gray-100);border-radius:4px;padding:10px 12px}
  .kpi-card--highlight{background:var(--navy-900);border-color:var(--navy-900);border-top:2.5px solid var(--meritz-orange)}
  .kpi-card--highlight .kpi-card__label,.kpi-card--highlight .kpi-card__value,.kpi-card--highlight .kpi-card__delta{color:var(--white)}
  .kpi-card__label{font-size:8pt;font-weight:600;color:var(--gray-500);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
  .kpi-card__value{font-size:20pt;font-weight:800;color:var(--navy-900);line-height:1.1}
  .kpi-card__delta{font-size:8.5pt;font-weight:600;margin-top:3px}
  .kpi-card__delta--positive{color:var(--positive)}.kpi-card__delta--negative{color:var(--negative)}
  .kpi-card--highlight .kpi-card__delta--positive{color:#6EE7B7}.kpi-card--highlight .kpi-card__delta--negative{color:#FCA5A5}
  .content-grid{display:grid;gap:12px;flex:1;align-content:start}
  .content-grid--2col{grid-template-columns:1fr 1fr}
  .content-grid--3col{grid-template-columns:1fr 1fr 1fr}
  .content-grid--60-40{grid-template-columns:3fr 2fr}
  .content-grid--1col{grid-template-columns:1fr}
  .content-grid--2x3{grid-template-columns:1fr 1fr 1fr;grid-template-rows:1fr 1fr}
  .panel{border:1px solid var(--gray-200);border-radius:4px;padding:10px;display:flex;flex-direction:column}
  .panel--borderless{border:none;padding:0}
  .panel__title{font-size:9.5pt;font-weight:700;color:var(--navy-800);margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--gray-100);display:flex;justify-content:space-between;align-items:baseline}
  .panel__title-unit{font-size:8pt;font-weight:400;color:var(--gray-400)}
  .panel__chart{flex:1;position:relative;min-height:0}
  .panel__bumper{font-size:8pt;color:var(--gray-500);margin-top:5px;padding-top:4px;border-top:1px solid var(--gray-100);line-height:1.4;font-style:italic}
  .data-table{width:100%;border-collapse:collapse;font-size:8.5pt;line-height:1.4}
  .data-table thead th{background:var(--navy-800);color:var(--white);font-weight:600;padding:5px 6px;text-align:left;font-size:8pt;white-space:nowrap}
  .data-table thead th:first-child{border-radius:3px 0 0 0}.data-table thead th:last-child{border-radius:0 3px 0 0}
  .data-table tbody td{padding:4px 6px;border-bottom:1px solid var(--gray-100)}
  .data-table tbody tr:nth-child(even){background:var(--gray-50)}
  .data-table .num{text-align:right;font-variant-numeric:tabular-nums}
  .data-table .bold{font-weight:700}.data-table .positive{color:var(--positive);font-weight:600}.data-table .negative{color:var(--negative);font-weight:600}
  .callout{background:#F0F5FA;border-left:3px solid var(--navy-600);padding:8px 12px;border-radius:0 4px 4px 0;margin-top:6px}
  .callout__label{font-size:7.5pt;font-weight:700;color:var(--navy-600);text-transform:uppercase;letter-spacing:.8px;margin-bottom:2px}
  .callout__text{font-size:9pt;color:var(--navy-900);line-height:1.5;font-weight:500}
  .legend{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:5px}
  .legend__item{display:flex;align-items:center;gap:4px;font-size:8pt;color:var(--gray-600)}
  .legend__dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}
  .page-footer{margin-top:auto;padding-top:6px;border-top:1px solid var(--gray-200);display:flex;justify-content:space-between;align-items:flex-end;flex-shrink:0}
  .page-footer__source{font-size:7.5pt;color:var(--gray-400);line-height:1.4;max-width:70%}
  .page-footer__page{font-size:8pt;font-weight:700;color:var(--meritz-orange)}
  .commentary{list-style:none;padding:0}
  .commentary li{font-size:8.5pt;line-height:1.5;padding:3px 0 3px 12px;position:relative;color:var(--gray-700);border-bottom:1px solid var(--gray-100)}
  .commentary li:last-child{border-bottom:none}
  .commentary li::before{content:'';position:absolute;left:0;top:9px;width:5px;height:5px;background:var(--navy-600);border-radius:50%}
  .divider{border:none;border-top:1px solid var(--gray-200);margin:6px 0}
  .mb-8{margin-bottom:8px}.mb-12{margin-bottom:12px}.mt-6{margin-top:6px}.mt-8{margin-top:8px}
</style>
</head>
<body>'''

HEADER = '''<div class="page-header"><div class="page-header__logo"><div class="page-header__logo-mark"><svg viewBox="0 0 120 30" xmlns="http://www.w3.org/2000/svg"><text x="0" y="23" font-family="'Pretendard',Arial,sans-serif" font-size="26" font-weight="800" letter-spacing="-1" fill="#EF3B24">meritz</text></svg></div><span class="page-header__company">IPO Analysis</span></div><div class="page-header__meta"><div class="page-header__confidential">Confidential</div><div>2026.03 | IPO Market Review</div></div></div>'''
SOURCE = 'Source: KRX KIND, DART 투자설명서. SPAC/합병상장 제외(별도 명시 시 포함). 2026년은 3월 20일 기준 YTD.'

def footer(n):
    return f'<div class="page-footer"><div class="page-footer__source">{SOURCE}</div><div class="page-footer__page">{n}</div></div>'

def insight_bullets(items):
    """3개 bullet Key Insight"""
    bullets = ''.join(f'<li>{item}</li>' for item in items)
    return f'<div class="callout mt-6"><div class="callout__label">Key Insight</div><ul class="commentary" style="margin-top:4px">{bullets}</ul></div>'

# ===== PAGE 1 =====
html += f'''
<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">10년간 IPO 시장은 연평균 73건 상장(SPAC 제외), 코스닥이 89%를 차지하며 2021년 초대형 딜이 정점</div><div class="slide-title__sub">2016-2025 유가증권/코스닥 시장별 상장건수, 공모규모, 평균 공모규모 추이 (SPAC 제외)</div></div>
  <div class="kpi-row">
    <div class="kpi-card kpi-card--highlight"><div class="kpi-card__label">10년 누적 상장</div><div class="kpi-card__value">738건</div><div class="kpi-card__delta kpi-card__delta--positive">유가 85 / 코스닥 653</div></div>
    <div class="kpi-card"><div class="kpi-card__label">누적 공모규모</div><div class="kpi-card__value">73.9조</div><div class="kpi-card__delta">유가 46.9조 / 코스닥 25.9조</div></div>
    <div class="kpi-card"><div class="kpi-card__label">2025 상장건수</div><div class="kpi-card__value">76건</div><div class="kpi-card__delta kpi-card__delta--negative">vs 2024 79건</div></div>
    <div class="kpi-card"><div class="kpi-card__label">2025 공모규모</div><div class="kpi-card__value">4.7조</div><div class="kpi-card__delta kpi-card__delta--positive">▲ 22% vs 2024</div></div>
  </div>
  <div class="content-grid content-grid--3col" style="flex:1;">
    <div class="panel"><div class="panel__title">연도별 상장건수<span class="panel__title-unit">건</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>유가증권</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>코스닥</div></div><div class="panel__chart"><canvas id="c1a"></canvas></div></div>
    <div class="panel"><div class="panel__title">연도별 공모규모<span class="panel__title-unit">조원</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>유가증권</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>코스닥</div></div><div class="panel__chart"><canvas id="c1b"></canvas></div></div>
    <div class="panel"><div class="panel__title">평균 공모규모<span class="panel__title-unit">억원</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>유가증권</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>코스닥</div></div><div class="panel__chart"><canvas id="c1c"></canvas></div></div>
  </div>
  {insight_bullets([
    '<strong>코스닥 압도적 비중:</strong> 전체 738건 중 코스닥 653건(89%), 유가증권 85건(11%). 코스닥이 IPO 시장의 주력',
    '<strong>2021년 초대형 딜 집중:</strong> 카카오뱅크·LG에너지솔루션 등으로 유가증권 공모규모 15.9조 기록, 역대 최고',
    '<strong>2025년 안정적 회복:</strong> 76건 상장, 공모규모 4.7조(+22% YoY). 건수는 소폭 감소했으나 딜 사이즈 확대'
  ])}
  {footer(1)}
</div>'''

# ===== PAGE 2 =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">코스닥 기술특례 상장이 2024년 54%까지 확대, SPAC은 2022년 45건 정점 후 감소 추세</div><div class="slide-title__sub">2021-2025 코스닥 시장 상장트랙별 건수 추이 (SPAC 포함)</div></div>
  <div class="content-grid content-grid--60-40" style="flex:1;">
    <div class="panel"><div class="panel__title">코스닥 상장트랙별 건수 추이<span class="panel__title-unit">건</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-6)"></div>일반</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-5)"></div>기술특례</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-3)"></div>성장성특례</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>이익미실현</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-4)"></div>SPAC</div></div><div class="panel__chart"><canvas id="c2"></canvas></div></div>
    <div class="panel panel--borderless" style="display:flex;flex-direction:column;gap:6px;">
      <div class="panel__title" style="border-bottom:1px solid var(--gray-200);padding-bottom:5px;">상장트랙 비중 (SPAC 제외 기준)</div>
      <table class="data-table"><thead><tr><th>트랙</th><th class="num">'21</th><th class="num">'22</th><th class="num">'23</th><th class="num">'24</th><th class="num">'25</th></tr></thead><tbody>
        <tr><td class="bold">일반</td><td class="num">52%</td><td class="num">53%</td><td class="num">53%</td><td class="num">41%</td><td class="num">45%</td></tr>
        <tr><td class="bold">기술특례</td><td class="num">34%</td><td class="num">39%</td><td class="num">42%</td><td class="num positive">54%</td><td class="num">48%</td></tr>
        <tr><td class="bold">성장성</td><td class="num">7%</td><td class="num">2%</td><td class="num">3%</td><td class="num">0%</td><td class="num">1%</td></tr>
        <tr><td class="bold">이익미실현</td><td class="num">7%</td><td class="num">6%</td><td class="num">3%</td><td class="num">4%</td><td class="num">6%</td></tr>
      </tbody></table>
      {insight_bullets([
        '<strong>기술특례 급성장:</strong> 2021년 34% → 2024년 54%로 비중 2배 확대. 바이오/IT 기술기업의 코스닥 진입 가속화',
        '<strong>SPAC 감소 추세:</strong> 2022년 45건 정점 → 2025년 25건. 금리 상승기 SPAC 매력 저하',
        '<strong>일반 트랙 안정:</strong> 일반 상장은 연 29-40건 수준 유지, 전체 비중은 기술특례에 밀려 축소'
      ])}
    </div>
  </div>
  {footer(2)}
</div>'''

# ===== PAGE 3 =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">바이오 지속 1위, AI/반도체/2차전지가 신흥 IPO 테마로 부상 중</div><div class="slide-title__sub">2016-2025 전방산업 기준 재분류 업종별 상장 건수 추이 (SPAC 제외)</div></div>
  <div class="content-grid content-grid--60-40" style="flex:1;">
    <div class="panel"><div class="panel__title">업종별 상장건수 추이<span class="panel__title-unit">건</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:#2558A3"></div>바이오</div><div class="legend__item"><div class="legend__dot" style="background:#2BA5A5"></div>IT</div><div class="legend__item"><div class="legend__dot" style="background:#E85D75"></div>AI</div><div class="legend__item"><div class="legend__dot" style="background:#D4A843"></div>반도체</div><div class="legend__item"><div class="legend__dot" style="background:#7B61A6"></div>2차전지</div><div class="legend__item"><div class="legend__dot" style="background:#C53030"></div>방산</div><div class="legend__item"><div class="legend__dot" style="background:#4A9EBF"></div>기계/장비</div><div class="legend__item"><div class="legend__dot" style="background:#8B6F47"></div>화학/소재</div><div class="legend__item"><div class="legend__dot" style="background:#D6D6D6"></div>기타</div></div><div class="panel__chart"><canvas id="c3"></canvas></div></div>
    <div class="panel panel--borderless" style="display:flex;flex-direction:column;gap:6px;">
      <div class="panel__title" style="border-bottom:1px solid var(--gray-200);padding-bottom:5px;">업종별 누적 (2016-2025)</div>
      <table class="data-table"><thead><tr><th>업종</th><th class="num">건수</th><th class="num">비중</th></tr></thead><tbody>
        <tr><td class="bold">바이오/헬스케어</td><td class="num">155</td><td class="num">21.0%</td></tr>
        <tr><td class="bold">IT/소프트웨어</td><td class="num">126</td><td class="num">17.1%</td></tr>
        <tr><td class="bold">기계/장비</td><td class="num">92</td><td class="num">12.5%</td></tr>
        <tr><td class="bold">화학/소재</td><td class="num">80</td><td class="num">10.8%</td></tr>
        <tr><td class="bold">소비재/유통</td><td class="num">63</td><td class="num">8.5%</td></tr>
        <tr><td class="bold">반도체/디스플레이</td><td class="num">46</td><td class="num">6.2%</td></tr>
        <tr><td class="bold">2차전지/에너지</td><td class="num">32</td><td class="num">4.3%</td></tr>
        <tr><td class="bold">엔터/미디어</td><td class="num">28</td><td class="num">3.8%</td></tr>
        <tr><td class="bold">AI (중복집계)</td><td class="num">26</td><td class="num">-</td></tr>
        <tr><td class="bold">금융</td><td class="num">26</td><td class="num">3.5%</td></tr>
        <tr><td class="bold">자동차/모빌리티</td><td class="num">22</td><td class="num">3.0%</td></tr>
        <tr><td class="bold">방산/우주항공</td><td class="num">13</td><td class="num">1.8%</td></tr>
      </tbody></table>
      {insight_bullets([
        '<strong>AI IPO 급증:</strong> 2025년 AI 관련 상장 7건으로 역대 최다. IT 업종 내 AI 비중이 50% 돌파',
        '<strong>바이오 견조:</strong> 10년간 155건(21%)으로 부동의 1위. 기술특례 제도와 함께 성장',
        '<strong>2차전지·방산 테마:</strong> 2차전지 밸류체인 32건, 방산/우주항공 13건. 2023년 이후 뚜렷한 증가세'
      ])}
    </div>
  </div>
  {footer(3)}
</div>'''

# ===== PAGE 4 =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">PER 기반 밸류에이션이 80-96%, 할인율 안정 속 EV/EBITDA 활용 확대·공모가 정상화</div><div class="slide-title__sub">2021-2025 평가방법, 멀티플 밴드, 할인율, 밴드 대비 확정공모가 비율 분석</div></div>
  <div class="content-grid content-grid--2x3" style="flex:1;">
    <div class="panel"><div class="panel__title">평가방법별 건수<span class="panel__title-unit">건</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>PER</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>EV/EBITDA</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-3)"></div>PBR</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-4)"></div>PSR</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-6)"></div>기타</div></div><div class="panel__chart"><canvas id="c4a"></canvas></div></div>
    <div class="panel"><div class="panel__title">PER 멀티플 밴드<span class="panel__title-unit">배(x)</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:rgba(37,88,163,.3)"></div>Q1~Q3</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>중위값</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-3)"></div>평균</div></div><div class="panel__chart"><canvas id="c4b"></canvas></div></div>
    <div class="panel"><div class="panel__title">할인율 추이 (평균)<span class="panel__title-unit">%</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-5)"></div>할인율 하단</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>할인율 상단</div></div><div class="panel__chart"><canvas id="c4c"></canvas></div></div>
    <div class="panel"><div class="panel__title">평가방법 비중<span class="panel__title-unit">%</span></div>
      <table class="data-table" style="font-size:8pt;"><thead><tr><th>방법</th><th class="num">'21</th><th class="num">'22</th><th class="num">'23</th><th class="num">'24</th><th class="num">'25</th></tr></thead><tbody>
        <tr><td class="bold">PER</td><td class="num">88%</td><td class="num">96%</td><td class="num">90%</td><td class="num">86%</td><td class="num">79%</td></tr>
        <tr><td class="bold">EV/EBITDA</td><td class="num">8%</td><td class="num">4%</td><td class="num">2%</td><td class="num">3%</td><td class="num positive">12%</td></tr>
        <tr><td class="bold">PBR</td><td class="num">2%</td><td class="num">-</td><td class="num">5%</td><td class="num">4%</td><td class="num">3%</td></tr>
        <tr><td class="bold">PSR</td><td class="num">1%</td><td class="num">-</td><td class="num">1%</td><td class="num">1%</td><td class="num">3%</td></tr>
      </tbody></table></div>
    <div class="panel"><div class="panel__title">EV/EBITDA 멀티플 밴드<span class="panel__title-unit">배(x)</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:rgba(43,165,165,.3)"></div>범위</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>중위값</div></div><div class="panel__chart"><canvas id="c4d"></canvas></div></div>
    <div class="panel"><div class="panel__title">밴드 대비 확정공모가 비율<span class="panel__title-unit">%, 중간값=100%</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>평균</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>중위값</div></div><div class="panel__chart"><canvas id="c4e"></canvas></div></div>
  </div>
  {insight_bullets([
    '<strong>PER 비중 하락 중:</strong> 2022년 96% → 2025년 79%. EV/EBITDA가 12%로 확대되며 인프라/에너지 기업 중심 다변화',
    '<strong>PER 멀티플 안정:</strong> PER 중위값 22-26배 유지. 할인율 하단 34-36%, 상단 22-26%로 5개년 안정적 밴드',
    '<strong>2024년 공모가 과열:</strong> 밴드 대비 129%까지 상승 후 2025년 104%로 정상화. 적정가 복귀'
  ])}
  {footer(4)}
</div>'''

# ===== PAGE 5 =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">참여기관 수 2배 증가에도 기관경쟁률은 제자리, 공모가는 밴드 상단 회귀</div><div class="slide-title__sub">2021-2025 수요예측 참여현황, 경쟁률, 공모가 밴드 대비 확정공모가 분석</div></div>
  <div class="kpi-row kpi-row--5">
    <div class="kpi-card kpi-card--highlight"><div class="kpi-card__label">2025 참여기관</div><div class="kpi-card__value">2,028</div><div class="kpi-card__delta kpi-card__delta--positive">▲ 74% vs '21</div></div>
    <div class="kpi-card"><div class="kpi-card__label">2025 기관경쟁률</div><div class="kpi-card__value">902:1</div><div class="kpi-card__delta kpi-card__delta--negative">▼ 24% vs '21</div></div>
    <div class="kpi-card"><div class="kpi-card__label">2025 청약경쟁률</div><div class="kpi-card__value">2,295:1</div><div class="kpi-card__delta kpi-card__delta--positive">▲ 95% vs '21</div></div>
    <div class="kpi-card"><div class="kpi-card__label">2024 밴드대비</div><div class="kpi-card__value">120%</div><div class="kpi-card__delta kpi-card__delta--positive">역대 최고</div></div>
    <div class="kpi-card"><div class="kpi-card__label">2025 밴드대비</div><div class="kpi-card__value">104%</div><div class="kpi-card__delta kpi-card__delta--negative">정상화 복귀</div></div>
  </div>
  <div class="content-grid content-grid--3col" style="flex:1;">
    <div class="panel"><div class="panel__title">참여기관(막대) / 기관경쟁률(선)<span class="panel__title-unit">좌:개사, 우::1</span></div><div class="panel__chart"><canvas id="c5a"></canvas></div></div>
    <div class="panel"><div class="panel__title">청약경쟁률 추이<span class="panel__title-unit">:1</span></div><div class="panel__chart"><canvas id="c5b"></canvas></div></div>
    <div class="panel"><div class="panel__title">밴드 대비 확정공모가<span class="panel__title-unit">%, 중간값=100%</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>평균</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>중위값</div></div><div class="panel__chart"><canvas id="c6"></canvas></div></div>
  </div>
  {insight_bullets([
    '<strong>참여기관 급증:</strong> 2021년 1,165개사 → 2025년 2,028개사(+74%). 기관투자자 IPO 관심 지속 확대',
    '<strong>경쟁률 역설:</strong> 기관 수 증가에도 경쟁률은 오히려 하락(1,181→902:1). 공급 확대가 수요 증가를 상쇄',
    '<strong>공모가 정상화:</strong> 2024년 과열(밴드 120%) 후 2025년 104%로 복귀. 청약경쟁률은 꾸준히 우상향(2,295:1)'
  ])}
  {footer(5)}
</div>'''

# ===== PAGE 6 =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">상장일 수익률은 높지만, 중장기 수익률은 2024년 급격히 악화 후 2025년 반등</div><div class="slide-title__sub">2021-2025 확정공모가 대비 시초가/종가/1개월/3개월/6개월 수익률 추이 (평균)</div></div>
  <div class="content-grid content-grid--3col" style="flex:1;">
    <div class="panel"><div class="panel__title">전체 연도별 구간 수익률<span class="panel__title-unit">%, 평균</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>시초가</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>종가</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-3)"></div>1개월</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-4)"></div>3개월</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-5)"></div>6개월</div></div><div class="panel__chart"><canvas id="c7"></canvas></div></div>
    <div class="panel"><div class="panel__title">코스닥 구간 수익률<span class="panel__title-unit">%, 평균</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>시초가</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>종가</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-3)"></div>1개월</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-4)"></div>3개월</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-5)"></div>6개월</div></div><div class="panel__chart"><canvas id="c7k"></canvas></div></div>
    <div class="panel"><div class="panel__title">유가증권 구간 수익률<span class="panel__title-unit">%, 평균</span></div><div class="legend"><div class="legend__item"><div class="legend__dot" style="background:var(--chart-1)"></div>시초가</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-2)"></div>종가</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-3)"></div>1개월</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-4)"></div>3개월</div><div class="legend__item"><div class="legend__dot" style="background:var(--chart-5)"></div>6개월</div></div><div class="panel__chart"><canvas id="c7y"></canvas></div></div>
  </div>
  <div class="content-grid content-grid--1col mt-6">
    <div class="panel panel--borderless">
      <table class="data-table"><thead><tr><th>구분</th><th class="num" colspan="5" style="text-align:center">전체</th><th class="num" colspan="5" style="text-align:center">코스닥</th><th class="num" colspan="5" style="text-align:center">유가증권</th></tr><tr><th></th><th class="num">'21</th><th class="num">'22</th><th class="num">'23</th><th class="num">'24</th><th class="num">'25</th><th class="num">'21</th><th class="num">'22</th><th class="num">'23</th><th class="num">'24</th><th class="num">'25</th><th class="num">'21</th><th class="num">'22</th><th class="num">'23</th><th class="num">'24</th><th class="num">'25</th></tr></thead><tbody>
        <tr><td class="bold">시초가</td><td class="num positive">55.9</td><td class="num positive">30.3</td><td class="num positive">85.7</td><td class="num positive">66.9</td><td class="num positive">90.5</td><td class="num positive">55.9</td><td class="num positive">30.1</td><td class="num positive">85.8</td><td class="num positive">69.8</td><td class="num positive">92.7</td><td class="num positive">55.9</td><td class="num positive">34.7</td><td class="num positive">84.5</td><td class="num positive">39.4</td><td class="num positive">70.7</td></tr>
        <tr><td class="bold">종가</td><td class="num positive">58.5</td><td class="num positive">28.9</td><td class="num positive">75.5</td><td class="num positive">42.8</td><td class="num positive">71.5</td><td class="num positive">57.6</td><td class="num positive">29.6</td><td class="num positive">74.6</td><td class="num positive">43.7</td><td class="num positive">73.4</td><td class="num positive">63.7</td><td class="num positive">18.4</td><td class="num positive">89.3</td><td class="num positive">34.4</td><td class="num positive">54.2</td></tr>
        <tr><td class="bold">1개월</td><td class="num positive">44.5</td><td class="num positive">20.8</td><td class="num positive">58.1</td><td class="num">3.3</td><td class="num positive">58.9</td><td class="num positive">44.0</td><td class="num positive">22.1</td><td class="num positive">56.6</td><td class="num">2.3</td><td class="num positive">60.8</td><td class="num positive">47.2</td><td class="num negative">-1.2</td><td class="num positive">81.2</td><td class="num positive">14.3</td><td class="num positive">40.3</td></tr>
        <tr><td class="bold">3개월</td><td class="num positive">33.6</td><td class="num positive">20.5</td><td class="num positive">40.6</td><td class="num negative">-5.9</td><td class="num positive">71.8</td><td class="num positive">33.3</td><td class="num positive">22.6</td><td class="num positive">32.7</td><td class="num negative">-9.7</td><td class="num positive">74.5</td><td class="num positive">35.6</td><td class="num negative">-14.4</td><td class="num positive">161.3</td><td class="num positive">31.8</td><td class="num positive">46.3</td></tr>
      </tbody></table>
    </div>
  </div>
  {insight_bullets([
    '<strong>2024년 경고등:</strong> 상장일 +67%였으나 1개월 +3%, 3개월 -6%. 공모가 과열(밴드 120%)이 중장기 마이너스로 귀결',
    '<strong>2025년 V자 반등:</strong> 전 구간 강한 회복. 코스닥 3개월 +74.5%, 유가증권 3개월 +46.3%',
    '<strong>유가증권 변동성:</strong> 유가증권은 2023년 3개월 +161% vs 2022년 -14%. 대형딜 구성에 따라 편차 극심'
  ])}
  {footer(6)}
</div>'''

# ===== PAGE 7 =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">기관경쟁률이 높을수록 밴드 상단 초과 확정 및 높은 청약경쟁률로 연결</div><div class="slide-title__sub">2021-2025 수요예측 경쟁률 vs 확정공모가 비율 / 청약경쟁률 산포도</div></div>
  <div class="content-grid content-grid--2col" style="flex:1;">
    <div class="panel"><div class="panel__title">기관경쟁률 vs 밴드대비 공모가<span class="panel__title-unit">X::1, Y:%</span></div><div class="panel__chart"><canvas id="c8a"></canvas></div><div class="panel__bumper">경쟁률 1,000:1+ 시 밴드 상단 초과(110%+) 확정 확률 크게 상승</div></div>
    <div class="panel"><div class="panel__title">기관경쟁률 vs 청약경쟁률<span class="panel__title-unit">X::1, Y::1</span></div><div class="panel__chart"><canvas id="c8b"></canvas></div><div class="panel__bumper">기관과 개인 수요가 동행. 기관경쟁 고조 시 청약도 과열</div></div>
  </div>
  {insight_bullets([
    '<strong>기관경쟁률 = 흥행 선행지표:</strong> 1,000:1 초과 시 확정공모가 평균 밴드 상단 115%, 청약경쟁률 3,000:1+',
    '<strong>기관-개인 수요 동행:</strong> 기관경쟁률이 높은 딜일수록 청약경쟁률도 비례 상승. 정보 비대칭 완화 효과',
    '<strong>500:1 미만 리스크:</strong> 기관경쟁률 500:1 미만 시 밴드 하단 확정 빈도 증가. 수요예측 부진 = 흥행 실패 신호'
  ])}
  {footer(7)}
</div>'''

# ===== PAGE 8 (수정: 4개 산포도 - 종가 2개 + 1개월 2개) =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">경쟁률은 종가 수익률과 양의 상관, 1개월 후에는 상관 약화</div><div class="slide-title__sub">경쟁률-수익률 상관관계 산포도 (2021-2025, 종가/1개월)</div></div>
  <div class="content-grid content-grid--2col" style="flex:1;">
    <div class="panel"><div class="panel__title">기관경쟁률 vs 종가 수익률<span class="panel__title-unit">X::1, Y:%</span></div><div class="panel__chart"><canvas id="c8c"></canvas></div></div>
    <div class="panel"><div class="panel__title">청약경쟁률 vs 종가 수익률<span class="panel__title-unit">X::1, Y:%</span></div><div class="panel__chart"><canvas id="c8d"></canvas></div></div>
    <div class="panel"><div class="panel__title">기관경쟁률 vs 1개월 수익률<span class="panel__title-unit">X::1, Y:%</span></div><div class="panel__chart"><canvas id="c8e"></canvas></div></div>
    <div class="panel"><div class="panel__title">청약경쟁률 vs 1개월 수익률<span class="panel__title-unit">X::1, Y:%</span></div><div class="panel__chart"><canvas id="c8f"></canvas></div></div>
  </div>
  {insight_bullets([
    '<strong>종가 수익률 상관:</strong> 기관경쟁률과 상장일 종가 수익률 간 양의 상관이 가장 뚜렷. 수요예측이 당일 성과를 좌우',
    '<strong>1개월 후 약화:</strong> 1개월 수익률은 경쟁률과의 상관이 현저히 약화. 시장 환경·실적이 중장기 성과 결정',
    '<strong>청약경쟁률도 유사 패턴:</strong> 개인 청약경쟁률도 종가와 양의 상관 → 1개월 후 약화. 단기 모멘텀 지표로 유효'
  ])}
  {footer(8)}
</div>'''

# ===== PAGE 9 =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">연초와 하반기 IPO가 공모가/수익률 모두 우수, 4-6월 비수기 패턴 존재</div><div class="slide-title__sub">2021-2025 월별 확정공모가 비율 및 종가 수익률</div></div>
  <div class="content-grid content-grid--2col" style="flex:1;">
    <div class="panel"><div class="panel__title">월별 밴드 대비 확정공모가<span class="panel__title-unit">%, 100%=밴드중간값</span></div><div class="panel__chart"><canvas id="c9a"></canvas></div></div>
    <div class="panel"><div class="panel__title">월별 종가 수익률<span class="panel__title-unit">%, 공모가 대비</span></div><div class="panel__chart"><canvas id="c9b"></canvas></div></div>
  </div>
  {insight_bullets([
    '<strong>상반기 비수기:</strong> 4-6월 공모가 밴드 하단 확정 및 수익률 저조 패턴 반복. IPO 타이밍 전략에 유의미한 시사점',
    '<strong>하반기 시즌:</strong> 10-12월 연말 시즌에 밴드 상단 초과 확정 빈도 상승. 특히 12월 수익률 변동폭 최대',
    '<strong>연초 강세:</strong> 1-3월 높은 공모가 비율과 수익률. 연초 투자심리 개선 및 양질의 딜 집중 경향'
  ])}
  {footer(9)}
</div>'''

# ===== PAGE 10 =====
html += f'''<div class="page">
  {HEADER}
  <div class="slide-title"><div class="slide-title__main">유통비율 20-30%대가 최적 구간(평균 84%), 공모규모 소형주에서 수익률 최고</div><div class="slide-title__sub">유통주식 비율 및 공모규모 구간별 종가 수익률 분석 (2021-2025)</div></div>
  <div class="content-grid content-grid--2col mb-12" style="flex:1;">
    <div class="panel"><div class="panel__title">유통비율 vs 종가 수익률<span class="panel__title-unit">X:%, Y:%</span></div><div class="panel__chart"><canvas id="c10"></canvas></div></div>
    <div class="panel"><div class="panel__title">공모규모 vs 종가 수익률<span class="panel__title-unit">X:억원(log), Y:%</span></div><div class="panel__chart"><canvas id="c11"></canvas></div></div>
  </div>
  <div class="content-grid content-grid--2col">
    <div class="panel panel--borderless"><div class="panel__title" style="border-bottom:1px solid var(--gray-200);padding-bottom:5px;">유통비율 구간별</div><table class="data-table"><thead><tr><th>구간</th><th class="num">건수</th><th class="num">평균</th><th class="num">중위값</th></tr></thead><tbody>
      <tr><td>10-20%</td><td class="num">26</td><td class="num positive">73.4%</td><td class="num">58.0%</td></tr>
      <tr><td class="bold">20-30%</td><td class="num">119</td><td class="num positive">84.3%</td><td class="num">72.0%</td></tr>
      <tr><td>30-40%</td><td class="num">149</td><td class="num positive">46.0%</td><td class="num">25.7%</td></tr>
      <tr><td>40-50%</td><td class="num">45</td><td class="num positive">32.2%</td><td class="num">16.6%</td></tr>
      <tr><td>50%+</td><td class="num">42</td><td class="num positive">28.7%</td><td class="num">10.9%</td></tr>
    </tbody></table></div>
    <div class="panel panel--borderless"><div class="panel__title" style="border-bottom:1px solid var(--gray-200);padding-bottom:5px;">공모규모 구간별</div><table class="data-table"><thead><tr><th>구간</th><th class="num">건수</th><th class="num">평균</th><th class="num">중위값</th></tr></thead><tbody>
      <tr><td>~100억</td><td class="num">16</td><td class="num positive">49.5%</td><td class="num">15.8%</td></tr>
      <tr><td class="bold">100-300억</td><td class="num">202</td><td class="num positive">60.7%</td><td class="num">39.4%</td></tr>
      <tr><td>300-500억</td><td class="num">80</td><td class="num positive">52.9%</td><td class="num">38.6%</td></tr>
      <tr><td>500-1,000억</td><td class="num">49</td><td class="num positive">47.5%</td><td class="num">23.3%</td></tr>
      <tr><td>1,000-5,000억</td><td class="num">24</td><td class="num positive">52.0%</td><td class="num">43.4%</td></tr>
      <tr><td>5,000억+</td><td class="num">13</td><td class="num positive">57.3%</td><td class="num">68.3%</td></tr>
    </tbody></table></div>
  </div>
  {insight_bullets([
    '<strong>유통비율 20-30%가 최적:</strong> 평균 수익률 84.3%(중위값 72.0%)로 압도적. 희소성 프리미엄이 수익률 견인',
    '<strong>유통비율 40%+ 주의:</strong> 유통비율이 높아질수록 수익률 급감. 50%+ 구간 평균 28.7%, 수급 부담 반영',
    '<strong>공모규모 무관:</strong> 규모별 수익률 편차는 크지 않으나, 5,000억+ 초대형 딜도 중위값 68.3%로 양호'
  ])}
  {footer(10)}
</div>'''

# ===== SCRIPT SECTION =====
html += f'''
<script>
  Chart.register(ChartDataLabels);
  Chart.defaults.font.family="'Pretendard',-apple-system,'Segoe UI',sans-serif";
  Chart.defaults.font.size=10;Chart.defaults.color='#6B6B6B';
  Chart.defaults.plugins.legend.display=false;
  Chart.defaults.plugins.tooltip.backgroundColor='#0B1D3A';
  Chart.defaults.plugins.tooltip.titleFont={{size:10,weight:'600'}};
  Chart.defaults.plugins.tooltip.bodyFont={{size:10}};
  Chart.defaults.plugins.tooltip.padding=8;Chart.defaults.plugins.tooltip.cornerRadius=3;
  Chart.defaults.scale.grid={{color:'#ECECEC',lineWidth:.8}};
  Chart.defaults.scale.border={{display:false}};
  Chart.defaults.elements.bar.borderRadius=2;Chart.defaults.elements.line.tension=.3;
  Chart.defaults.plugins.datalabels={{display:false}};

  const C1='#2558A3',C2='#2BA5A5',C3='#D4A843',C4='#7B61A6',C5='#C53030',C6='#8E8E8E',C7='#E85D75';
  const Y10=['2016','2017','2018','2019','2020','2021','2022','2023','2024','2025'];
  const Y5=['2021','2022','2023','2024','2025'];
  const DL_BAR={{display:true,anchor:'end',align:'end',font:{{size:8,weight:'600'}},color:'#404040',formatter:v=>{{if(Array.isArray(v))return'';return v===0?'':v}}}};
  const DL_LINE={{display:true,anchor:'end',align:'top',font:{{size:8}},color:'#404040',offset:2,formatter:v=>v===0?'':v.toLocaleString()}};
  const DL_STACK={{display:true,anchor:'center',align:'center',font:{{size:7,weight:'600'}},color:'#fff',formatter:v=>v===0?'':v}};

  // P1
  new Chart(document.getElementById('c1a'),{{type:'bar',data:{{labels:Y10,datasets:[{{label:'유가',data:[14,9,8,9,5,13,4,6,9,7],backgroundColor:C1,datalabels:DL_STACK}},{{label:'코스닥',data:[49,51,70,64,62,73,66,76,70,69],backgroundColor:C2,datalabels:DL_STACK}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{stacked:true,grid:{{display:false}}}},y:{{stacked:true,ticks:{{callback:v=>v+'건'}}}}}}}}}});
  new Chart(document.getElementById('c1b'),{{type:'bar',data:{{labels:Y10,datasets:[{{label:'유가',data:[42586,44484,7136,11374,21123,158749,131455,10870,18468,22008],backgroundColor:C1,datalabels:{{display:false}}}},{{label:'코스닥',data:[19509,31545,18979,21179,22480,32760,24883,22454,20353,22693],backgroundColor:C2,datalabels:{{display:false}}}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{datalabels:{{display:true,anchor:'end',align:'end',font:{{size:7}},color:'#404040',formatter:(v,ctx)=>{{const ds=ctx.chart.data.datasets;const idx=ctx.dataIndex;if(ctx.datasetIndex===ds.length-1){{const total=ds.reduce((s,d)=>s+d.data[idx],0);return (total/10000).toFixed(1)+'조'}}return''}}}}}},scales:{{x:{{stacked:true,grid:{{display:false}}}},y:{{stacked:true,ticks:{{callback:v=>(v/10000).toFixed(1)+'조'}}}}}}}}}});
  new Chart(document.getElementById('c1c'),{{type:'line',data:{{labels:Y10,datasets:[{{label:'유가',data:[3042,4943,892,1264,4225,12211,32864,1812,2052,3144],borderColor:C1,backgroundColor:'rgba(37,88,163,.08)',fill:true,pointRadius:3,pointBackgroundColor:C1,borderWidth:2,datalabels:{{display:true,anchor:'end',align:'top',font:{{size:7}},color:C1,formatter:v=>v>=10000?(v/10000).toFixed(1)+'만':v.toLocaleString()}}}},{{label:'코스닥',data:[398,619,271,331,363,449,377,295,291,329],borderColor:C2,fill:false,pointRadius:3,pointBackgroundColor:C2,borderWidth:2,datalabels:{{display:true,anchor:'end',align:'bottom',font:{{size:7}},color:C2,formatter:v=>v.toLocaleString()}}}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{ticks:{{callback:v=>v.toLocaleString()+'억'}}}}}}}}}});

  // P2
  new Chart(document.getElementById('c2'),{{type:'bar',data:{{labels:Y5,datasets:[{{label:'일반',data:[38,35,40,29,31],backgroundColor:C6,datalabels:DL_STACK}},{{label:'기술특례',data:[25,26,32,38,33],backgroundColor:C5,datalabels:DL_STACK}},{{label:'성장성',data:[5,1,2,0,1],backgroundColor:C3,datalabels:DL_STACK}},{{label:'이익미실현',data:[5,4,2,3,4],backgroundColor:C2,datalabels:DL_STACK}},{{label:'SPAC',data:[24,45,37,40,25],backgroundColor:C4,datalabels:DL_STACK}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{stacked:true,grid:{{display:false}}}},y:{{stacked:true,ticks:{{callback:v=>v+'건'}}}}}}}}}});

  // P3 - 업종 세분화 + AI
  new Chart(document.getElementById('c3'),{{type:'bar',data:{{labels:Y10,datasets:[
    {{label:'바이오',data:[12,6,24,16,22,17,12,10,18,18],backgroundColor:'#2558A3',datalabels:{{display:false}}}},
    {{label:'IT',data:[7,9,10,16,9,25,9,17,10,14],backgroundColor:'#2BA5A5',datalabels:{{display:false}}}},
    {{label:'AI(중복)',data:[0,0,0,3,5,5,3,1,2,7],backgroundColor:'transparent',borderColor:'#E85D75',borderWidth:2,type:'line',pointRadius:4,pointBackgroundColor:'#E85D75',fill:false,yAxisID:'y1',datalabels:{{display:true,anchor:'end',align:'top',font:{{size:8,weight:'700'}},color:'#E85D75',formatter:v=>v===0?'':v}}}},
    {{label:'반도체',data:[3,4,1,3,6,3,6,9,6,5],backgroundColor:'#D4A843',datalabels:{{display:false}}}},
    {{label:'2차전지',data:[1,1,2,5,2,3,6,3,7,2],backgroundColor:'#7B61A6',datalabels:{{display:false}}}},
    {{label:'방산',data:[0,2,2,1,1,1,0,0,3,3],backgroundColor:'#C53030',datalabels:{{display:false}}}},
    {{label:'기계/장비',data:[2,12,10,6,8,9,12,7,15,11],backgroundColor:'#4A9EBF',datalabels:{{display:false}}}},
    {{label:'화학/소재',data:[8,8,5,6,5,8,8,17,4,11],backgroundColor:'#8B6F47',datalabels:{{display:false}}}},
    {{label:'기타',data:[30,18,24,20,14,20,17,18,16,5],backgroundColor:'#D6D6D6',datalabels:{{display:false}}}}
  ]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{stacked:true,grid:{{display:false}}}},y:{{stacked:true,ticks:{{callback:v=>v+'건'}}}},y1:{{display:false,min:0,max:30}}}}}}}});

  // P4
  new Chart(document.getElementById('c4a'),{{type:'bar',data:{{labels:Y5,datasets:[{{label:'PER',data:[76,67,74,68,60],backgroundColor:C1,datalabels:DL_STACK}},{{label:'EV/EBITDA',data:[7,3,2,3,11],backgroundColor:C2,datalabels:DL_STACK}},{{label:'PBR',data:[2,0,4,3,2],backgroundColor:C3,datalabels:DL_STACK}},{{label:'PSR',data:[1,0,1,1,2],backgroundColor:C4,datalabels:DL_STACK}},{{label:'기타',data:[0,0,1,4,1],backgroundColor:C6,datalabels:DL_STACK}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{stacked:true,grid:{{display:false}}}},y:{{stacked:true,ticks:{{callback:v=>v+'건'}}}}}}}}}});
  new Chart(document.getElementById('c4b'),{{type:'bar',data:{{labels:Y5,datasets:[{{label:'Q1-Q3',data:[[21.0,30.6],[16.6,28.6],[18.3,26.8],[19.9,28.4],[21.4,29.0]],backgroundColor:'rgba(37,88,163,.25)',borderColor:C1,borderWidth:1,datalabels:{{display:false}}}},{{type:'line',label:'중위값',data:[26.1,23.8,22.1,25.3,25.5],borderColor:C1,backgroundColor:C1,pointRadius:5,pointStyle:'rectRot',borderWidth:2,fill:false,datalabels:DL_LINE}},{{type:'line',label:'평균',data:[25.2,22.6,22.5,25.1,25.7],borderColor:C3,backgroundColor:C3,pointRadius:4,borderWidth:1.5,borderDash:[4,3],fill:false,datalabels:{{display:false}}}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{min:10,max:40,ticks:{{callback:v=>v+'x'}}}}}}}}}});
  new Chart(document.getElementById('c4c'),{{type:'line',data:{{labels:Y5,datasets:[{{label:'하단',data:[34.5,36.4,34.6,34.4,35.5],borderColor:C5,backgroundColor:'rgba(197,48,48,.08)',fill:true,pointRadius:4,pointBackgroundColor:C5,borderWidth:2,datalabels:{{display:true,anchor:'end',align:'top',font:{{size:8}},color:C5,formatter:v=>v+'%'}}}},{{label:'상단',data:[23.3,24.3,22.5,22.5,26.3],borderColor:C1,backgroundColor:'rgba(37,88,163,.08)',fill:true,pointRadius:4,pointBackgroundColor:C1,borderWidth:2,datalabels:{{display:true,anchor:'end',align:'bottom',font:{{size:8}},color:C1,formatter:v=>v+'%'}}}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{min:15,max:45,ticks:{{callback:v=>v+'%'}}}}}}}}}});
  // P4 EV/EBITDA band
  new Chart(document.getElementById('c4d'),{{type:'bar',data:{{labels:['2021','2022','2024','2025'],datasets:[{{label:'범위',data:[[2.0,49.2],[35.6,82.5],[22.5,33.4],[7.9,31.5]],backgroundColor:'rgba(43,165,165,.25)',borderColor:C2,borderWidth:1,datalabels:{{display:false}}}},{{type:'line',label:'중위값',data:[21.0,42.7,24.0,16.1],borderColor:C2,backgroundColor:C2,pointRadius:5,pointStyle:'rectRot',borderWidth:2,fill:false,datalabels:{{display:true,anchor:'end',align:'top',font:{{size:9,weight:'600'}},color:C2,formatter:v=>v+'x'}}}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{min:0,max:90,ticks:{{callback:v=>v+'x'}}}}}}}}}});
  // P4 밴드대비 확정공모가 비율
  new Chart(document.getElementById('c4e'),{{type:'line',data:{{labels:Y5,datasets:[{{label:'평균',data:[112.3,95.5,110.2,129.4,103.7],borderColor:C1,backgroundColor:'rgba(37,88,163,.1)',fill:true,pointRadius:5,pointBackgroundColor:C1,borderWidth:2.5,datalabels:{{display:true,anchor:'end',align:'top',font:{{size:9,weight:'600'}},color:C1,formatter:v=>v+'%'}}}},{{label:'중위값',data:[112.5,105.9,112.1,129.9,107.7],borderColor:C2,pointRadius:4,pointBackgroundColor:C2,borderWidth:2,borderDash:[4,3],fill:false,datalabels:{{display:true,anchor:'end',align:'bottom',font:{{size:8}},color:C2,formatter:v=>v+'%'}}}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{min:85,max:140,ticks:{{callback:v=>v+'%'}}}}}}}}}});

  // P5
  new Chart(document.getElementById('c5a'),{{type:'bar',data:{{labels:Y5,datasets:[{{label:'참여기관(막대)',data:[1165,955,1508,1847,2028],backgroundColor:C1,yAxisID:'y',order:2,datalabels:DL_BAR}},{{type:'line',label:'기관경쟁률(선)',data:[1181,836,939,771,902],borderColor:C3,backgroundColor:C3,pointRadius:5,pointBackgroundColor:C3,borderWidth:2.5,yAxisID:'y1',fill:false,order:1,datalabels:{{display:true,anchor:'end',align:'top',font:{{size:9,weight:'700'}},color:'#B8860B',formatter:v=>v.toLocaleString()+':1'}}}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{position:'left',ticks:{{callback:v=>v.toLocaleString()}}}},y1:{{position:'right',grid:{{display:false}},ticks:{{callback:v=>v+':1'}}}}}}}}}});
  new Chart(document.getElementById('c5b'),{{type:'bar',data:{{labels:Y5,datasets:[{{label:'청약',data:[1177,1473,1951,2051,2295],backgroundColor:C2,datalabels:DL_BAR}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{ticks:{{callback:v=>v.toLocaleString()+':1'}}}}}}}}}});
  new Chart(document.getElementById('c6'),{{type:'line',data:{{labels:Y5,datasets:[{{label:'평균',data:[110.5,95.7,109.8,120.1,103.6],borderColor:C1,backgroundColor:'rgba(37,88,163,.1)',fill:true,pointRadius:5,pointBackgroundColor:C1,borderWidth:2.5,datalabels:DL_LINE}},{{label:'중위값',data:[112.5,106.2,112.2,129.0,107.7],borderColor:C2,pointRadius:4,pointBackgroundColor:C2,borderWidth:2,borderDash:[4,3],fill:false,datalabels:{{display:false}}}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{min:85,max:135,ticks:{{callback:v=>v+'%'}}}}}}}}}});

  // P6
  function makeReturnChart(id, openD, closeD, m1D, m3D, m6D){{
    new Chart(document.getElementById(id),{{type:'bar',data:{{labels:Y5,datasets:[
      {{label:'시초가',data:openD,backgroundColor:C1,datalabels:{{display:false}}}},
      {{label:'종가',data:closeD,backgroundColor:C2,datalabels:{{display:false}}}},
      {{label:'1개월',data:m1D,backgroundColor:C3,datalabels:{{display:false}}}},
      {{label:'3개월',data:m3D,backgroundColor:C4,datalabels:{{display:false}}}},
      {{label:'6개월',data:m6D,backgroundColor:C5,datalabels:{{display:false}}}}
    ]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{grid:{{display:false}}}},y:{{ticks:{{callback:v=>v+'%'}}}}}}}}}});
  }}
  makeReturnChart('c7',[55.9,30.3,85.7,66.9,90.5],[58.5,28.9,75.5,42.8,71.5],[44.5,20.8,58.1,3.3,58.9],[33.6,20.5,40.6,-5.9,71.8],[35.4,26.9,29.0,-2.3,65.4]);
  makeReturnChart('c7k',[55.9,30.1,85.8,69.8,92.7],[57.6,29.6,74.6,43.7,73.4],[44.0,22.1,56.6,2.3,60.8],[33.3,22.6,32.7,-9.7,74.5],[34.2,29.6,26.2,-10.1,68.2]);
  makeReturnChart('c7y',[55.9,34.7,84.5,39.4,70.7],[63.7,18.4,89.3,34.4,54.2],[47.2,-1.2,81.2,14.3,40.3],[35.6,-14.4,161.3,31.8,46.3],[41.9,-17.5,72.0,75.6,38.8]);

  // Scatter Data
  const SD={sd_data};
  function mk(d,xK,yK,c){{return{{data:d.filter(r=>r[xK]!=null&&r[yK]!=null).map(r=>({{x:r[xK],y:r[yK]}})),backgroundColor:c+'60',borderColor:c,borderWidth:.8,pointRadius:2.5,pointHoverRadius:5}}}}
  // P7
  new Chart(document.getElementById('c8a'),{{type:'scatter',data:{{datasets:[{{label:'기관vs공모가',...mk(SD,'x_inst','y_price',C1)}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{datalabels:{{display:false}}}},scales:{{x:{{title:{{display:true,text:'기관경쟁률(:1)',font:{{size:9}}}},ticks:{{callback:v=>v.toLocaleString()}}}},y:{{title:{{display:true,text:'밴드대비 공모가(%)',font:{{size:9}}}},ticks:{{callback:v=>v+'%'}}}}}}}}}});
  new Chart(document.getElementById('c8b'),{{type:'scatter',data:{{datasets:[{{label:'기관vs청약',...mk(SD,'x_inst','y_sub',C2)}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{datalabels:{{display:false}}}},scales:{{x:{{title:{{display:true,text:'기관경쟁률(:1)',font:{{size:9}}}},ticks:{{callback:v=>v.toLocaleString()}}}},y:{{title:{{display:true,text:'청약경쟁률(:1)',font:{{size:9}}}},ticks:{{callback:v=>v.toLocaleString()}}}}}}}}}});
  // P8 - 4개 산포도 (종가 + 1개월)
  function mkScatter(canvasId, xKey, yKey, color, xLabel, yLabel){{
    new Chart(document.getElementById(canvasId),{{type:'scatter',data:{{datasets:[{{label:yLabel,...mk(SD,xKey,yKey,color)}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{datalabels:{{display:false}}}},scales:{{x:{{title:{{display:true,text:xLabel,font:{{size:9}}}},ticks:{{callback:v=>v.toLocaleString()}}}},y:{{title:{{display:true,text:yLabel,font:{{size:9}}}},ticks:{{callback:v=>v+'%'}}}}}}}}}});
  }}
  mkScatter('c8c','x_inst','y_close',C2,'기관경쟁률(:1)','종가 수익률(%)');
  mkScatter('c8d','y_sub','y_close',C2,'청약경쟁률(:1)','종가 수익률(%)');
  mkScatter('c8e','x_inst','y_1m',C3,'기관경쟁률(:1)','1개월 수익률(%)');
  mkScatter('c8f','y_sub','y_1m',C3,'청약경쟁률(:1)','1개월 수익률(%)');

  // P9 Monthly
  const M=['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'];
  const mR={{2021:[113.8,119.7,118.1,122.2,113.7,108.2,111.3,111.5,103.9,97.1,110.1,76.4],2022:[106.7,100.5,96.2,122.8,103.8,92.7,98.0,100.9,80.1,96.0,88.8,57.7],2023:[94.7,105.8,108.3,98.5,103.7,101.0,118.9,115.6,108.0,114.0,115.7,103.7],2024:[125.9,129.2,141.3,140.5,134.7,135.1,131.4,111.4,130.6,119.9,112.0,79.0],2025:[75.5,102.3,91.3,107.7,107.2,108.3,108.3,104.2,107.3,112.6,108.9,109.0]}};
  const mC={{2021:[96.7,79.6,86.0,99.6,33.9,49.3,45.5,61.1,43.3,26.4,54.9,11.2],2022:[82.1,24.4,55.8,137.4,43.3,-2.1,27.4,32.4,3.6,31.8,-0.3,28.1],2023:[98.2,137.8,74.5,6.9,33.9,80.6,48.5,40.1,97.8,44.5,66.7,196.6],2024:[181.7,87.2,107.2,99.8,86.5,36.2,7.6,36.5,35.4,9.4,-9.6,27.2],2025:[-14.4,68.2,37.5,15.9,93.8,75.2,47.4,48.9,81.4,110.2,123.3,116.0]}};
  const yC=[C1,C2,C3,C4,C5];
  new Chart(document.getElementById('c9a'),{{type:'line',data:{{labels:M,datasets:Object.keys(mR).map((y,i)=>({{label:y,data:mR[y],borderColor:yC[i],backgroundColor:'transparent',pointRadius:2.5,pointBackgroundColor:yC[i],borderWidth:1.8,fill:false,datalabels:{{display:false}}}}))
  }},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:true,position:'top',labels:{{boxWidth:10,font:{{size:9}},padding:8}}}}}},scales:{{x:{{grid:{{display:false}}}},y:{{min:50,max:150,ticks:{{callback:v=>v+'%'}}}}}}}}}});
  new Chart(document.getElementById('c9b'),{{type:'line',data:{{labels:M,datasets:Object.keys(mC).map((y,i)=>({{label:y,data:mC[y],borderColor:yC[i],backgroundColor:'transparent',pointRadius:2.5,pointBackgroundColor:yC[i],borderWidth:1.8,fill:false,datalabels:{{display:false}}}}))
  }},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:true,position:'top',labels:{{boxWidth:10,font:{{size:9}},padding:8}}}}}},scales:{{x:{{grid:{{display:false}}}},y:{{ticks:{{callback:v=>v+'%'}}}}}}}}}});

  // P10
  new Chart(document.getElementById('c10'),{{type:'scatter',data:{{datasets:[{{label:'유통비율vs종가',data:SD.filter(d=>d.float&&d.y_close!=null).map(d=>({{x:d.float,y:d.y_close}})),backgroundColor:C1+'50',borderColor:C1,borderWidth:.8,pointRadius:2.5}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{datalabels:{{display:false}}}},scales:{{x:{{title:{{display:true,text:'유통비율(%)',font:{{size:9}}}},min:0,max:100,ticks:{{callback:v=>v+'%'}}}},y:{{title:{{display:true,text:'종가수익률(%)',font:{{size:9}}}},ticks:{{callback:v=>v+'%'}}}}}}}}}});
  new Chart(document.getElementById('c11'),{{type:'scatter',data:{{datasets:[{{label:'공모규모vs종가',data:SD.filter(d=>d.size&&d.y_close!=null).map(d=>({{x:d.size,y:d.y_close}})),backgroundColor:C2+'50',borderColor:C2,borderWidth:.8,pointRadius:2.5}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{datalabels:{{display:false}}}},scales:{{x:{{type:'logarithmic',title:{{display:true,text:'공모규모(억원,log)',font:{{size:9}}}},ticks:{{callback:v=>v.toLocaleString()}}}},y:{{title:{{display:true,text:'종가수익률(%)',font:{{size:9}}}},ticks:{{callback:v=>v+'%'}}}}}}}}}});
</script>
</body>
</html>'''

with open('ipo_report.html', 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Done! {len(html)} bytes written')
