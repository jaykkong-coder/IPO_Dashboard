# IPO Dashboard

## 프로젝트 개요
KRX KIND 신규상장 법인 목록 + DART 투자설명서 밸류에이션 데이터를 DB화하고 Streamlit 대시보드로 시각화.

- **GitHub**: https://github.com/jaykkong-coder/IPO_Dashboard
- **Streamlit Cloud**: 배포 완료
- **DART API 키**: 359212a47d6222104789f5d610aa3896471f8227

## 아키텍처

```
KIND 크롤링 → DART API → 투자설명서 다운로드 → HTML 파싱 → SQLite → Streamlit
```

| 파일 | 역할 |
|------|------|
| `dashboard.py` | Streamlit 대시보드 (차트, 시계열, 통계) |
| `ipo_extractor.py` | 투자설명서 파서 (핵심, 800줄+) |
| `pipeline.py` | 일괄 처리 (KIND → DART API → 파싱 → DB) |
| `reparse.py` | 캐시 문서 재파싱 (네트워크 불필요) |
| `kind_scraper.py` | KRX KIND 크롤러 |
| `database.py` | SQLite 스키마 + upsert |
| `dev_test.py` | 파서 개발용 테스트 스크립트 |

## 핵심 의사결정

1. **SPAC 제외**: 회사명/업종에 "스팩/SPAC/기업인수목적" 포함 시 skip
2. **합병상장 제외**: 투자설명서 앞 2000자에 "합병" 키워드 → skip
3. **정정 후 값 우선**: `reversed(tables)` 로 뒤에서부터 검색
4. **주당 평가가액 산출 내역 테이블 1순위**: 공모주식수/신주/구주/상장후주식수의 가장 정확한 소스
5. **발행제비용 테이블**: 인수수수료 + 수수료율의 가장 정확한 소스
6. **EV/EBITDA 적정시총**: EV - 순차입금 - 비지배지분 + 공모유입자금
7. **연환산/LTM = 일반기업** (추정치가 아님)

## 파싱 주의사항

### 용어 변형 (같은 값, 다른 표현)
- 멀티플: 유사기업PER, 비교회사PER, 비교대상회사PER, 비교기업PER
- 단위: "45.5배", "25.72(배)", "30.91X", 별도셀 ['배', '1.80']
- 적용이익: 당기순이익, 순이익, EBITDA, 매출액, 자본총계

### 단위 변환
- 백만원, 천원, 원 → 모두 백만원으로 통일
- 발행제비용 단위 판단: 합계 < 10만 → 백만원, 10만~1억 → 천원, 1억+ → 원

### 증권사 인식
- "증권" or "금융투자" or "인터내셔날" 포함
- "증권의종류" 같은 헤더 제외

## 업데이트 방법

```bash
# 신규 회사 추가 (DART API 필요)
python3 pipeline.py

# 파서 수정 후 재파싱 (네트워크 불필요)
python3 reparse.py

# 파서 개발 중 빠른 테스트
python3 dev_test.py              # 전체 재파싱 + 검증
python3 dev_test.py 리브스메드     # 특정 회사만 테스트

# GitHub 배포
git add -A && git commit -m "update" && git push
```

## 현재 데이터 범위
- 2025.01 ~ 2026.03 신규상장 80건
- 향후 과거(2024년~) 및 미래 확장 예정
