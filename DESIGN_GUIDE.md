# IB 리포트 디자인 가이드 (메리츠 스타일)

`ipo_report.html`에서 확립한 컨설팅/IB 장표 디자인 시스템.
**새 보고서를 만들 때는 `report_template.html`을 복사해서 시작한다.**

## 파일
| 파일 | 용도 |
|------|------|
| `report_template.html` | 새 보고서 시작점 (표지 + 예시 페이지 + Chart.js 설정 내장) |
| `ipo_report.html` | 실전 적용 사례 (11페이지 — 차트 패턴 참고용) |
| `design_system.html` | 초기 디자인 시스템 레퍼런스 문서 |

## 페이지 규격
- **A4 가로** (297×210mm), 페이지당 `<div class="page">` 하나
- 여백: 상 14mm / 하 12mm / 좌우 16mm (CSS 변수 `--page-margin-*`)
- PDF 변환: Playwright `page.pdf(width="297mm", height="210mm", print_background=True, prefer_css_page_size=True)` — 마진 0

## 컬러 토큰 (CSS `:root`)
- **브랜드**: `--meritz-orange: #EF3B24` (로고·강조선 전용, 남용 금지)
- **네이비**: `--navy-900: #0B1D3A` ~ `--navy-500` (제목·강조 텍스트)
- **그레이 스케일**: `--gray-900: #1A1A1A` ~ `--gray-50` (본문은 gray-900, 보조 gray-500~600)
- **차트 팔레트**: 웜그레이 계열 `C1 #58534D, C2 #9E9A94, C3 #4A8EC2, C4 #CCC7BF, C5 #9E8C63, C6 #E8E4DE` + 강조 `HL #2558A3`
  - 원칙: **차트는 저채도 웜그레이, 말하고 싶은 시리즈 1개만 블루(HL)로 강조**
- 판정색: positive `#1A8754`, negative `#C53030`

## 타이포그래피
- 폰트: Pretendard (CDN), 본문 13pt
- 페이지 헤드메시지(`slide-title__main`): **결론을 문장으로** ("~ 증가추세", "~ 수렴하는 경향") — 차트 나열식 제목 금지
- 부제(`slide-title__sub`): 데이터 범위·기준 명시 (예: "2021-2026.1H 확정공모가 대비 …")
- 숫자 강조: `font-weight:700` + 데이터레이블 12pt

## 페이지 구조 (위→아래)
1. `page-header` — meritz 로고(SVG 텍스트) + 섹션명 | Confidential + 문서명
2. `slide-title` — 헤드메시지 + 부제
3. `content-grid` — 패널 배치: `--1col / --2col / --3col / --2x2 / --60-40` 변형
4. `panel` — `panel__title`(+`panel__title-unit` 단위) + `panel__chart`(canvas)
5. `callout` — **Key Insight 불릿 2~4개** (`<strong>소제목:</strong> 근거 수치 포함 서술`)
6. `page-footer` — Source 표기 + 페이지 번호

## 차트 규칙 (Chart.js 4.x + datalabels 플러그인)
- 전역: `devicePixelRatio:3`(인쇄 선명도), legend 기본 숨김, 그리드 `#ECECEC`
- 막대 radius 2, 라인 tension .3, 포인트 5px
- 데이터레이블: 위쪽 anchor/end, 12pt bold, `#404040` (강조 시리즈는 HL색)
- 규제/이벤트 주석: afterDraw 플러그인으로 말풍선 (ipo_report.html의 `p4bBubble` 참고)
- 분기 평균선 등 파생 표기: 플러그인으로 자동 계산 (`qAvgPlugin` 참고)

## 표지 (SVG 벡터)
- 흰 배경 + 레드 리본 웨이브(베지어 2밴드 + 오버랩 폴드) + 하단 회색 바
- 텍스트: 좌상단 Confidential → 오렌지 강조선 + 제목(40pt/800) + 부제 → 지표 2개(오렌지 좌측 보더) → 회색 바 안에 날짜
- 리본 색·곡선은 SVG path/gradient 수정으로 조정 가능 (해상도 무한)

## 콘텐츠 작법 원칙
1. **페이지 = 주장 1개.** 헤드메시지가 결론, 차트가 근거, Key Insight가 해석.
2. 반기·부분 기간 데이터는 라벨에 명시 (`'26.1H`) — 완결 연도와 섞을 때 주의
3. 미성숙 지표(예: 6개월 수익률)는 공란(null)으로 — 억지로 채우지 않음
4. Source 줄에 모집단 기준 명시 (예: "SPAC/합병상장 제외(별도 명시 시 포함)")

## PDF 생성
```bash
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={'width':1400,'height':990}, device_scale_factor=2)
    pg.goto('file:///절대경로/보고서.html', wait_until='networkidle')
    pg.wait_for_timeout(2500)  # 차트 렌더 대기
    pg.pdf(path='보고서.pdf', width='297mm', height='210mm',
           margin={'top':'0','bottom':'0','left':'0','right':'0'},
           print_background=True, prefer_css_page_size=True)
    b.close()"
```
