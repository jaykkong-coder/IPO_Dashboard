# IPO Dashboard

2016~2026년 한국 신규상장(IPO) 기업의 밸류에이션 데이터를 자동 수집 / 분석하는 대시보드

## Live Demo
[Streamlit Cloud에서 보기](https://jaykkong-coder-ipo-dashboard.streamlit.app)

## 데이터 현황

| 항목 | 수치 |
|------|------|
| 기간 | 2016 ~ 2026 (11년) |
| 총 기업수 | 722건 |
| 시장 | 코스닥 + 유가증권 |
| 제외 | SPAC, 합병상장, 사채/유증, 리츠, 분할/재상장 |

### 연도별 분포
| 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|------|------|------|------|------|------|------|------|------|------|------|
| 51 | 55 | 75 | 79 | 71 | 83 | 69 | 81 | 77 | 75 | 6 |

### 수집 항목
- **밸류에이션**: 평가방법(PER/EV/EBITDA/PSR/PBR), 적용멀티플, 적용이익, 적정시가총액, 할인율, 주당평가가액
- **공모가**: 공모가밴드, 확정공모가, 공모가 위치(상단/하단)
- **공모규모**: 기준시가총액, 공모금액, 공모비율, 신주/구주, 유통가능주식수
- **기타**: 대표주관회사, 인수수수료/수수료율, 상장유형(기술특례/일반)
- **수요예측/청약**: 기관경쟁률, 의무보유확약비율, 청약경쟁률(비례)

### 데이터 소스
| 소스 | 용도 |
|------|------|
| [KRX KIND](https://kind.krx.co.kr) | 상장법인 목록, 업종, 주요제품 |
| [DART OpenAPI](https://opendart.fss.or.kr) | 투자설명서 원문 다운로드 + 파싱 |
| [38커뮤니케이션](http://www.38.co.kr) | 기관경쟁률, 의무보유확약, 청약경쟁률 |

## 기술 스택
- Python, Streamlit, Plotly
- BeautifulSoup (HTML/XML 파싱)
- SQLite

## 파일 구조
```
dashboard.py        # Streamlit 대시보드
ipo_extractor.py    # 투자설명서 파서 (핵심)
pipeline.py         # KIND → DART → 파싱 → DB 파이프라인
reparse.py          # 캐시 문서 재파싱
scraper_38.py       # 38커뮤니케이션 크롤러
database.py         # SQLite DB
dev_test.py         # 파서 개발용 테스트
kind_scraper.py     # KRX KIND 크롤러
```

## 사용법
```bash
# 신규 회사 추가 (DART API 필요)
python3 pipeline.py

# 파서 수정 후 재파싱
python3 reparse.py

# 38커뮤니케이션 데이터 수집
python3 scraper_38.py

# 대시보드 실행
streamlit run dashboard.py
```
