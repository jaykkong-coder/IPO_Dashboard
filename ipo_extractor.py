"""
IPO 투자설명서 데이터 추출기
DART 투자설명서 원문(XML/HTML)에서 밸류에이션 관련 데이터를 구조화하여 추출
"""

import re
import os
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def parse_number(text):
    """텍스트에서 숫자 추출 (콤마 제거, 단위 처리)"""
    if not text:
        return None
    text = text.strip()
    # "75,474원" → 75474, "42,995백만원" → 42995
    cleaned = re.sub(r'[^\d.\-]', '', text.replace(',', ''))
    if not cleaned or cleaned in ('-', '.'):
        return None
    try:
        if '.' in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return None


def parse_percentage(text):
    """퍼센트 문자열에서 숫자 추출"""
    if not text:
        return None
    match = re.search(r'([\d.]+)\s*%', text)
    if match:
        return float(match.group(1))
    return None


def parse_range(text):
    """범위 문자열 파싱 "41.70% ~ 27.13%" → (41.70, 27.13)"""
    if not text:
        return None, None
    # 퍼센트 범위
    pct_match = re.findall(r'([\d.]+)\s*%', text)
    if len(pct_match) >= 2:
        return float(pct_match[0]), float(pct_match[1])
    # 원 범위
    won_match = re.findall(r'([\d,]+)\s*원', text)
    if len(won_match) >= 2:
        return parse_number(won_match[0]), parse_number(won_match[1])
    return None, None


def extract_tables(html_content):
    """HTML에서 모든 테이블을 행/열 데이터로 추출"""
    soup = BeautifulSoup(html_content, "lxml")
    tables = []
    for i, table in enumerate(soup.find_all("table")):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            flat = " ".join(" ".join(r) for r in rows)
            tables.append({"index": i, "rows": rows, "flat": flat})
    return tables


def find_tables_with_keywords(tables, keywords, top_n=5):
    """키워드 점수가 높은 테이블 반환"""
    scored = []
    for t in tables:
        score = sum(1 for kw in keywords if kw in t["flat"])
        if score > 0:
            scored.append((t, score))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_n]


def cell_contains(row, keyword):
    """행의 셀 중 키워드를 포함하는 셀이 있는지"""
    for cell in row:
        if keyword in cell:
            return True
    return False


def get_cell_value(rows, label_keyword, value_col=None):
    """테이블에서 label_keyword를 포함하는 행의 값 셀을 반환"""
    for row in rows:
        for i, cell in enumerate(row):
            if label_keyword in cell:
                # 같은 행에서 label이 아닌 다음 셀 반환
                if value_col is not None and value_col < len(row):
                    return row[value_col]
                # label 셀 다음의 값 셀들을 반환
                remaining = [c for j, c in enumerate(row) if j != i and c.strip()]
                if remaining:
                    return remaining[0]
    return None


class IPOExtractor:
    """투자설명서에서 IPO 밸류에이션 데이터 추출"""

    def __init__(self, html_content):
        self.tables = extract_tables(html_content)
        self.data = {}

    def extract_all(self):
        """모든 필드 추출"""
        self._extract_underwriter()
        self._extract_valuation()
        self._extract_text_fallback()  # 테이블에서 못 찾은 것을 본문 텍스트에서 추출
        self._extract_discount_and_band()
        self._extract_confirmed_price()
        self._extract_shares()
        self._extract_float()
        self._extract_fees()
        self._extract_listing_type()
        self._detect_spac_merger()
        self._calculate_derived()
        return self.data

    def _extract_underwriter(self):
        """대표주관회사, 인수단, 인수수수료(인수대가 칼럼에서)"""
        candidates = find_tables_with_keywords(
            self.tables,
            ["인수인", "대표주관", "인수수량", "인수금액", "인수방법", "인수대가"]
        )
        underwriters = []
        total_fee_from_table = 0
        for t, score in candidates:
            if score < 2:
                continue
            rows = t["rows"]

            # 헤더에서 "인수대가" 칼럼 인덱스 찾기
            fee_col = None
            for row in rows:
                for idx, cell in enumerate(row):
                    if "인수대가" in cell:
                        fee_col = idx
                        break
                if fee_col is not None:
                    break

            for row in rows:
                joined = " ".join(row)
                # "대표주관", "공동대표", 또는 셀 값이 "대표"인 경우
                is_underwriter_row = (
                    "대표주관" in joined or "공동대표" in joined
                    or any(cell.strip() == "대표" for cell in row)
                    or any(cell.strip() == "대표주관회사" for cell in row)
                )
                if is_underwriter_row:
                    for cell in row:
                        clean = cell.replace("㈜", "").replace("(주)", "").strip()
                        # 증권사/금융투자사 이름 매칭
                        is_firm = (
                            ("증권" in clean and "종류" not in clean)
                            or "금융투자" in clean
                            or "인터내셔날" in clean
                        )
                        if is_firm and "대표" not in clean and "인수" not in clean and len(clean) < 30:
                            if clean not in underwriters:
                                underwriters.append(clean)
                    # 인수대가 칼럼에서 수수료 추출
                    if fee_col is not None and fee_col < len(row):
                        num = parse_number(row[fee_col])
                        if num and 10000000 < num < 50000000000:
                            total_fee_from_table += num
            if underwriters:
                break

        self.data["대표주관회사"] = ", ".join(underwriters) if underwriters else None
        self.data["인수단"] = self.data["대표주관회사"]

        if total_fee_from_table > 0:
            self.data["_인수대가합계"] = total_fee_from_table

    def _find_number_in_row(self, row, min_val=0, unit=None):
        """행의 셀에서 숫자 찾기 (단위가 별도 셀인 경우도 처리)"""
        for i, cell in enumerate(row):
            if unit and cell.strip() == unit:
                # 단위 셀 다음 셀에 숫자가 있을 수 있음
                if i + 1 < len(row):
                    num = parse_number(row[i + 1])
                    if num and num > min_val:
                        return num
                # 단위 셀 이전 셀에 숫자
                if i - 1 >= 0:
                    num = parse_number(row[i - 1])
                    if num and num > min_val:
                        return num
            # 숫자+단위가 한 셀에 있는 경우
            if unit:
                match = re.search(rf'([\d,.]+)\s*{re.escape(unit)}', cell)
                if match:
                    num = parse_number(match.group(1))
                    if num and num > min_val:
                        return num
            else:
                num = parse_number(cell)
                if num and num > min_val:
                    return num
        return None

    def _extract_valuation(self):
        """평가방법, 적용멀티플, 적용이익, 주당평가가액"""
        # 공모가산정요약표 / 밸류에이션 핵심 테이블 찾기
        candidates = find_tables_with_keywords(
            self.tables,
            ["평가방법", "평가모형", "적용산식", "주당 평가가액", "주당평가가액", "공모가 산정"]
        )

        for t, score in candidates:
            rows = t["rows"]
            for row in rows:
                joined = " ".join(row)

                # 평가방법: "상대가치법" 등 알려진 값만
                if "평가방법" in joined and "평가방법" not in self.data:
                    for cell in row:
                        c = cell.strip()
                        if c in ("상대가치법", "상대가치", "절대가치법", "DCF"):
                            self.data["평가방법"] = c
                            break

                # 평가모형 (PER, PSR, PBR, EV/EBITDA 등) - 알려진 값만 매칭
                if "평가모형" in joined and "평가모형" not in self.data:
                    known_models = ["PER", "PSR", "PBR", "EV/EBITDA", "EV/Sales"]
                    for cell in row:
                        cell_upper = cell.strip().upper()
                        for model in known_models:
                            if model in cell_upper:
                                self.data["평가모형"] = model
                                break
                        if "평가모형" in self.data:
                            break

                # 적용멀티플: ② 행에서 PER/PSR/PBR/EV/EBITDA 배수 추출
                mult_labels = ["유사기업", "유사회사", "비교대상회사", "비교대상", "비교회사",
                               "비교기업", "적용 PER", "적용 PSR", "적용 PBR",
                               "적용PER", "적용PSR", "적용PBR", "적용 EV", "EV/EBITDA"]
                mult_models = ["PER", "PSR", "PBR", "EV", "EBITDA"]
                if any(lbl in joined for lbl in mult_labels) and any(m in joined for m in mult_models):
                    if "적용멀티플" not in self.data:
                        # 패턴1: "45.5배", "19.87.", "25.72(배)" (같은 셀)
                        match = re.search(r'([\d]+\.[\d]+|[\d]+)\s*[\(]?[배x]', joined)
                        if match:
                            val = float(match.group(1))
                            if 0.1 < val < 500:
                                self.data["적용멀티플"] = val
                        # 패턴2: 셀 구조 ['②', '유사기업 PBR', '배', '1.80', ...]
                        # "배" 셀 다음에 숫자 셀
                        if "적용멀티플" not in self.data:
                            for idx, cell in enumerate(row):
                                if cell.strip() == "배" and idx + 1 < len(row):
                                    num = parse_number(row[idx + 1])
                                    if num and 0.1 < num < 500:
                                        self.data["적용멀티플"] = float(num)
                                        break
                        # 패턴3: "25.46배", "30.91X" 등 독립 셀
                        if "적용멀티플" not in self.data:
                            for cell in row:
                                m = re.match(r'^([\d]+\.[\d]+|[\d]+)\s*[배xX]?\.?$', cell.strip())
                                if m:
                                    val = float(m.group(1))
                                    if 0.1 < val < 500:
                                        self.data["적용멀티플"] = val
                                        break
                        # 패턴4: "30.91X" 패턴 (X 단위, 여러개면 평균)
                        if "적용멀티플" not in self.data:
                            x_vals = re.findall(r'([\d]+\.[\d]+)\s*[Xx]', joined)
                            if x_vals:
                                vals = [float(v) for v in x_vals if 0.1 < float(v) < 500]
                                if vals:
                                    self.data["적용멀티플"] = round(sum(vals) / len(vals), 2)

                # 적용이익: ① 행 (당기순이익, EBITDA, 매출액, 자본총계 등)
                if "①" in joined:
                    earnings_labels = ["당기순이익", "순이익", "매출액", "EBITDA", "영업이익", "자본총계"]
                    if any(lbl in joined for lbl in earnings_labels):
                        if "적용이익_백만원" not in self.data:
                            # 패턴1: "42,995백만원" 또는 "4,644(백만원)"
                            match = re.search(r'([\d,]+)\s*[\(]?백만원', joined)
                            if match:
                                self.data["적용이익_백만원"] = parse_number(match.group(1))
                            # 패턴2: "4,511,714천원" → 백만원으로 변환
                            if "적용이익_백만원" not in self.data:
                                match = re.search(r'([\-]?[\d,]+)\s*[\(]?천원', joined)
                                if match:
                                    val = parse_number(match.group(1))
                                    if val and abs(val) > 100:
                                        self.data["적용이익_백만원"] = round(val / 1000, 2)
                            # 패턴3: 단위 "백만원" 별도 셀
                            if "적용이익_백만원" not in self.data:
                                for idx, cell in enumerate(row):
                                    if cell.strip() == "백만원":
                                        if idx + 1 < len(row):
                                            num = parse_number(row[idx + 1])
                                            if num and num > 10:
                                                self.data["적용이익_백만원"] = num
                                                break
                                        if idx - 1 >= 0:
                                            num = parse_number(row[idx - 1])
                                            if num and num > 10:
                                                self.data["적용이익_백만원"] = num
                                                break
                            # 패턴4: 단위 "천원" 별도 셀
                            if "적용이익_백만원" not in self.data:
                                for idx, cell in enumerate(row):
                                    if cell.strip() == "천원":
                                        if idx + 1 < len(row):
                                            num = parse_number(row[idx + 1])
                                            if num and abs(num) > 100:
                                                self.data["적용이익_백만원"] = round(num / 1000, 2)
                                                break
                            # 패턴5: 단위 "원" 별도 셀 (10,053,667,329원 → 백만원 변환)
                            if "적용이익_백만원" not in self.data:
                                for idx, cell in enumerate(row):
                                    if cell.strip() == "원":
                                        if idx + 1 < len(row):
                                            num = parse_number(row[idx + 1])
                                            if num and abs(num) > 100000000:  # 1억원 이상
                                                self.data["적용이익_백만원"] = round(num / 1000000, 2)
                                                break

                # EV/EBITDA 전용: 순차입금, 비지배지분, 공모유입자금
                ev_fields = [
                    ("순차입금", "_순차입금_백만원"),
                    ("비지배지분", "_비지배지분_백만원"),
                    ("공모유입", "_공모유입자금_백만원"),
                ]
                for keyword, field_name in ev_fields:
                    if keyword in joined and field_name not in self.data:
                        # 같은 셀에 숫자+단위
                        for unit_str, divisor in [("백만원", 1), ("천원", 1000), ("원", 1000000)]:
                            match = re.search(rf'([\-]?[\d,]+)\s*[\(]?{unit_str}', joined)
                            if match:
                                val = parse_number(match.group(1))
                                if val is not None:
                                    self.data[field_name] = round(val / divisor, 2)
                                break
                        # 별도 셀
                        if field_name not in self.data:
                            for idx, cell in enumerate(row):
                                if cell.strip() in ("백만원", "천원", "원") and idx + 1 < len(row):
                                    num = parse_number(row[idx + 1])
                                    if num is not None:
                                        divisor = {"백만원": 1, "천원": 1000, "원": 1000000}[cell.strip()]
                                        self.data[field_name] = round(num / divisor, 2)
                                        break

                # 주당 평가가액 - 첫 셀(라벨)에 "주당" + "평가" + "가액"이 있어야 함
                # ① 행의 참고사항에 "주당 평가가액 산출"이 있어서 오탐 방지
                first_cells = " ".join(row[:2]) if len(row) >= 2 else joined
                if ("주당 평가가액" in first_cells or "주당평가가액" in first_cells or "주당 평가 가액" in first_cells):
                    if "주당평가가액" not in self.data:
                        # 패턴1: "75,474원" (라벨 셀 제외하고 검색)
                        for cell in row[1:]:
                            match = re.search(r'([\d,]+)\s*원', cell)
                            if match:
                                val = parse_number(match.group(1))
                                if val and 100 < val < 1000000:  # 100원~100만원
                                    self.data["주당평가가액"] = val
                                    break
                        # 패턴2: 단위 "원" 별도 셀 → 다음 셀에 숫자
                        if "주당평가가액" not in self.data:
                            for idx, cell in enumerate(row):
                                if cell.strip() == "원" and idx + 1 < len(row):
                                    num = parse_number(row[idx + 1])
                                    if num and 100 < num < 1000000:
                                        self.data["주당평가가액"] = num
                                        break

            # 확정공모가도 같은 테이블에 있을 수 있음
            for row in rows:
                joined = " ".join(row)
                if "확정공모가" in joined:
                    match = re.search(r'([\d,]+)\s*원', joined)
                    if match:
                        val = parse_number(match.group(1))
                        if val and val > 100:
                            self.data["확정공모가"] = val
                    if "확정공모가" not in self.data:
                        for idx, cell in enumerate(row):
                            if cell.strip() == "원" and idx + 1 < len(row):
                                num = parse_number(row[idx + 1])
                                if num and num > 100:
                                    self.data["확정공모가"] = num
                                    break

        # 2차 검색: 별도 요약표에서 (할인율/밴드와 같은 테이블)
        if "주당평가가액" not in self.data:
            for t in self.tables:
                flat = " ".join(" ".join(r) for r in t["rows"])
                if ("주당 평가가액" in flat or "주당평가가액" in flat or "상대가치 주당" in flat) and ("할인율" in flat or "밴드" in flat):
                    for row in t["rows"]:
                        first_cells = " ".join(row[:2]) if len(row) >= 2 else " ".join(row)
                        if "주당" in first_cells and "평가" in first_cells:
                            for cell in row[1:]:
                                match = re.search(r'([\d,]+)\s*원?', cell)
                                if match:
                                    val = parse_number(match.group(1))
                                    if val and 100 < val < 1000000:
                                        self.data["주당평가가액"] = val
                                        break
                            if "주당평가가액" not in self.data:
                                for idx, cell in enumerate(row):
                                    if cell.strip() == "원" and idx + 1 < len(row):
                                        num = parse_number(row[idx + 1])
                                        if num and 100 < num < 1000000:
                                            self.data["주당평가가액"] = num
                                            break
                    if "주당평가가액" in self.data:
                        break

        # 3차: 구버전 패턴 (2021~2022)
        # ['구 분', '산출 내역', '비고'] 구조의 주당 평가가액 산출 테이블
        # 3차는 멀티플/이익/시총/주당평가가액/주식수 중 하나라도 없으면 실행
        needs_old = not all(k in self.data for k in ["적용멀티플", "적용이익_백만원", "주당평가가액"])
        if needs_old:
            for t in reversed(self.tables):
                flat = " ".join(" ".join(r) for r in t["rows"])
                has_per = ("적용 PER" in flat or "PER 배수" in flat or "PER배수" in flat
                           or "적용 EV" in flat or "EV/EBITDA" in flat
                           or "평균 PER" in flat or "PER 평균" in flat
                           or "평균 EV" in flat
                           or "유사회사" in flat or "비교회사" in flat
                           or "적용 Multiple" in flat or "적용Multiple" in flat
                           or "Multiple" in flat or "멀티플" in flat
                           or "P/E" in flat or "P/B" in flat or "P/S" in flat)
                has_eval = (("평가가액" in flat or "평가 가액" in flat or "적정시가총액" in flat
                            or "기업가치" in flat)
                           and ("시가총액" in flat or "기업가치" in flat or "주당" in flat or "EBITDA" in flat))
                # 위험요소 테이블 제외
                first3 = " ".join(" ".join(r) for r in t["rows"][:3])
                is_risk = "사업위험" in first3 or "회사위험" in first3
                # 제외할 테이블: 투자지표 설명, 비교기업 PER 산출 (여러 회사 비교)
                is_exclude = ("투자지표의 부적합성" in flat or "제외 투자지표" in flat
                              or "제외투자지표" in flat or "투자지표의 적합성" in flat
                              or "발행주식총수" in flat)  # 비교기업 PER 산출 테이블 특징
                if has_per and has_eval and len(t["rows"]) >= 4 and not is_risk and not is_exclude:
                    mult_kws = ["적용 PER", "PER 배수", "PER배수", "적용 EV", "평균 PER",
                                "평균 EV/EBITDA", "유사회사 평균", "비교회사 평균", "유사회사 PER",
                                "비교기업 PER", "비교회사 PER",
                                "EV/EBITDA 거래배수", "거래배수", "적용 PSR", "적용 PBR",
                                "평균 PSR", "평균 PBR",
                                "적용 Multiple", "적용Multiple",
                                "PER 평균", "평균PER", "Multiple",
                                "적용 멀티플", "적용멀티플", "적용 P/E", "평균 P/E",
                                "적용 P/B", "평균 P/B", "적용 P/S", "적용P/S", "평균 P/S",
                                "PER(배)", "PBR(배)", "PSR(배)",
                                "유사회사 평균 PER", "평균 PER(배)"]
                    for row in t["rows"]:
                        joined = " ".join(row)

                        # 적용 투자지표 / 평가모형
                        if "적용 투자지표" in joined and "평가모형" not in self.data:
                            for cell in row:
                                cell_upper = cell.strip().upper()
                                for model in ["PER", "PSR", "PBR", "EV/EBITDA"]:
                                    if model in cell_upper:
                                        self.data["평가모형"] = model
                                        break

                        if any(kw in joined for kw in mult_kws) and "적용멀티플" not in self.data:
                            # "27.90배" 또는 "25.07" (배 없이 숫자만)
                            match = re.search(r'([\d]+\.[\d]+|[\d]+)\s*[\(]?배?', joined)
                            if match:
                                val = float(match.group(1))
                                if 1 < val < 500:
                                    self.data["적용멀티플"] = val
                                    if "평가모형" not in self.data:
                                        if "PER" in joined or "P/E" in joined:
                                            self.data["평가모형"] = "PER"
                                        elif "EV/EBITDA" in joined or "EBITDA" in joined:
                                            self.data["평가모형"] = "EV/EBITDA"
                                        elif "PSR" in joined or "P/S" in joined:
                                            self.data["평가모형"] = "PSR"
                                        elif "PBR" in joined or "P/B" in joined:
                                            self.data["평가모형"] = "PBR"

                        # 구버전 테이블은 가장 정확한 소스 → 기존값 덮어쓰기 허용

                        # 추정 당기순이익 / 적용 당기순이익 / 적용 순이익 / EBITDA
                        earnings_kws = ["당기순이익", "EBITDA", "적용 순이익", "적용순이익", "적용 당기순이익",
                                        "연환산 매출액", "적용 매출액", "적용매출액"]
                        if any(ek in joined for ek in earnings_kws):
                            skip_kw = ["현가", "현재가치", "적용주식수", "적용 주식수", "주당순이익", "주당 순이익"]
                            if not any(sk in joined for sk in skip_kw):
                                # 백만원 단위
                                match = re.search(r'([\d,]+)\s*백만원', joined)
                                if match:
                                    self.data["적용이익_백만원"] = parse_number(match.group(1))
                                else:
                                    # 원 단위 (단위 없이 숫자만 or "원" 표기)
                                    for cell in row[1:]:
                                        num = parse_number(cell)
                                        if num and num > 1000000000:  # 10억 이상이면 원 단위
                                            self.data["적용이익_백만원"] = round(num / 1000000, 2)
                                            break

                        # 평가 시가총액 / 기업가치 평가액 / 적정시가총액
                        cap_kws = ["평가 시가총액", "기업가치 평가액", "적정시가총액", "기업가치평가액",
                                   "적용 시가총액", "적정시가총액", "평가시가총액"]
                        if any(kw in joined for kw in cap_kws):
                            if "적용주식수" not in joined and "기준시가" not in joined:
                                # 백만원 단위
                                match = re.search(r'([\d,]+)\s*백만원', joined)
                                if match:
                                    val = parse_number(match.group(1))
                                    if val and val > 100:
                                        self.data["적정시가총액_백만원"] = val
                                        self.data["적정시가총액_억원"] = round(val / 100, 2)
                                # 억원 단위
                                if "적정시가총액_억원" not in self.data:
                                    match = re.search(r'([\d,]+)\s*억원', joined)
                                    if match:
                                        val = parse_number(match.group(1))
                                        if val and val > 1:
                                            self.data["적정시가총액_억원"] = val

                        # 주당 평가가액/평가가격/평가가치
                        if ("주당 평가가액" in joined or "주당 평가 가액" in joined
                            or "주당 평가가격" in joined or "주당평가가격" in joined
                            or "주당 평가 가치" in joined or "주당 평가가치" in joined):
                            match = re.search(r'([\d,]+)\s*원', joined)
                            if match:
                                val = parse_number(match.group(1))
                                if val and 100 < val < 1000000:
                                    self.data["주당평가가액"] = val

                        # 적용주식수 / 공모 후 주식수
                        if "적용주식수" in joined or "적용 주식수" in joined or "공모 후 주식수" in joined or "공모후 주식수" in joined:
                            match = re.search(r'([\d,]+)\s*주?', joined)
                            if match:
                                val = parse_number(match.group(1))
                                if val and 100000 < val < 500000000:
                                    self.data["상장후주식수"] = val

                    if "적용멀티플" in self.data:
                        break

    def _extract_text_fallback(self):
        """4차: 테이블에서 못 찾은 값을 본문 텍스트에서 정규식으로 추출 (구버전 대응)"""
        full_text = " ".join(t["flat"] for t in self.tables)
        # &cr; 등 HTML 엔티티 잔여물 제거
        full_text = full_text.replace("&cr;", " ").replace("&amp;", "&")

        # 적용멀티플: 다양한 텍스트 패턴
        if "적용멀티플" not in self.data:
            for model, aliases in [
                ("PER", ["PER", "P/E"]),
                ("EV/EBITDA", ["EV/EBITDA", "EV/Capacity", "EV/Pipeline"]),
                ("PSR", ["PSR", "P/S"]),
                ("PBR", ["PBR", "P/B"]),
            ]:
                for alias in aliases:
                    patterns = [
                        # "적용 PER(평균) 33.7", "적용PER(배) 35.4"
                        rf'적용\s*{re.escape(alias)}\s*[\(\(]?[평균배x]*[\)\)]?\s*([\d.]+)',
                        # "PER 평균은 10.19배"
                        rf'{re.escape(alias)}\s*(?:평균은?|배수는?|은|의 평균은?)\s*([\d.]+)\s*배?',
                        # "적용 PER 배수 12.84"
                        rf'적용\s*{re.escape(alias)}\s*배수\s*([\d.]+)',
                        # "평균 PER(배) 12.01"
                        rf'평균\s*{re.escape(alias)}\s*[\(\(]?배?[\)\)]?\s*([\d.]+)',
                        # "PER 30.4배 27.0배" (2열)
                        rf'{re.escape(alias)}\s*([\d.]+)\s*배?\s+[\d.]',
                        # "적용 P/S 거래배수 1.59"
                        rf'적용\s*{re.escape(alias)}\s*거래배수\s*[\(\(]?[배]?[\)\)]?\s*([\d.]+)',
                    ]
                    for pat in patterns:
                        match = re.search(pat, full_text)
                        if match:
                            val = float(match.group(1))
                            if 1 < val < 500:
                                self.data["적용멀티플"] = val
                                if "평가모형" not in self.data:
                                    self.data["평가모형"] = model
                                break
                    if "적용멀티플" in self.data:
                        break
                if "적용멀티플" in self.data:
                    break

        # 주당 평가가액: "주당 평가가액은 XX,XXX원" 또는 "주당 평가가액에 할인율"
        if "주당평가가액" not in self.data:
            match = re.search(r'주당\s*평가가액\w*\s*([\d,]+)\s*원', full_text)
            if match:
                val = parse_number(match.group(1))
                if val and 100 < val < 1000000:
                    self.data["주당평가가액"] = val

        # 할인율: "할인율 35.96%~26.11%" 또는 "할인율 59.78% ~ 50.52%"
        if "할인율_하단" not in self.data:
            match = re.search(r'할인율\s*([\d.]+)\s*%\s*~\s*([\d.]+)\s*%', full_text)
            if match:
                v1, v2 = float(match.group(1)), float(match.group(2))
                if 1 < v1 < 80 and 1 < v2 < 80:
                    self.data["할인율_하단"] = max(v1, v2)
                    self.data["할인율_상단"] = min(v1, v2)

        # 희망공모가액: "희망 공모가액 XX,XXX원 ~ XX,XXX원"
        if "공모가밴드_하단" not in self.data:
            match = re.search(r'희망\s*공모가액\s*([\d,]+)\s*원?\s*~\s*([\d,]+)\s*원', full_text)
            if match:
                v1, v2 = parse_number(match.group(1)), parse_number(match.group(2))
                if v1 and v2 and 100 < v1 < 1000000:
                    self.data["공모가밴드_하단"] = min(v1, v2)
                    self.data["공모가밴드_상단"] = max(v1, v2)
                    self.data["공모가밴드_중간값"] = (v1 + v2) / 2

    def _extract_discount_and_band(self):
        """할인율, 공모가밴드 - 밸류에이션 요약 테이블에서 추출"""
        # 핵심 요약 테이블 찾기 (평가가액 + 할인율 + 공모가밴드가 같이 있는 테이블)
        candidates = find_tables_with_keywords(
            self.tables,
            ["주당 평가가액", "할인율", "희망공모가액", "공모가액"]
        )

        for t, score in candidates:
            if score < 2:
                continue
            rows = t["rows"]
            for row in rows:
                joined = " ".join(row)
                first_cells = " ".join(row[:2]) if len(row) >= 2 else joined

                # 할인율: 라벨에 "할인율"이 있는 행 (① 행의 참고 "할인율" 오탐 방지)
                if "할인율" in first_cells and "%" in joined and "①" not in first_cells:
                    # 다양한 % 패턴: "35.41%", "47.6%", "34.53%~29.08%"
                    pcts = re.findall(r'(\d+\.?\d*)\s*%', joined)
                    if len(pcts) >= 2:
                        try:
                            vals = [float(p) for p in pcts if 1 < float(p) < 80]
                            if len(vals) >= 2:
                                self.data["할인율_하단"] = max(vals[:2])
                                self.data["할인율_상단"] = min(vals[:2])
                        except ValueError:
                            pass

                # 공모가밴드: "44,000원 ~ 55,000원" 또는 "45,000 ~ 58,000" (원 없이)
                if ("희망" in first_cells or "밴드" in first_cells or "공모가액" in first_cells) and "~" in joined:
                    # 패턴1: 숫자+원
                    prices = re.findall(r'([\d,]+)\s*원', joined)
                    # 패턴2: 숫자 ~ 숫자 (원 없이)
                    if len(prices) < 2:
                        prices = re.findall(r'([\d,]+)\s*~\s*([\d,]+)', joined)
                        if prices:
                            prices = list(prices[0])
                    if len(prices) >= 2:
                        vals = [parse_number(p) for p in prices]
                        vals = [v for v in vals if v and 100 < v < 1000000]
                        if len(vals) >= 2:
                            self.data["공모가밴드_하단"] = min(vals[:2])
                            self.data["공모가밴드_상단"] = max(vals[:2])
                            self.data["공모가밴드_중간값"] = (self.data["공모가밴드_하단"] + self.data["공모가밴드_상단"]) / 2

        # 2차 검색: 별도 요약표에서 할인율/밴드 찾기
        if "할인율_하단" not in self.data:
            for t in self.tables:
                flat = " ".join(" ".join(r) for r in t["rows"])
                if "할인율" in flat and "%" in flat and ("평가가액" in flat or "밴드" in flat or "희망" in flat):
                    for row in t["rows"]:
                        first_cells = " ".join(row[:2]) if len(row) >= 2 else " ".join(row)
                        joined = " ".join(row)
                        if "할인율" in first_cells and "%" in joined and "①" not in first_cells:
                            pcts = re.findall(r'(\d+\.?\d*)\s*%', joined)
                            if len(pcts) >= 2:
                                try:
                                    vals = [float(p) for p in pcts if 1 < float(p) < 80]
                                    if len(vals) >= 2:
                                        self.data["할인율_하단"] = max(vals[:2])
                                        self.data["할인율_상단"] = min(vals[:2])
                                except ValueError:
                                    pass
                    if "할인율_하단" in self.data:
                        break

        if "공모가밴드_하단" not in self.data:
            for t in self.tables:
                flat = " ".join(" ".join(r) for r in t["rows"])
                if ("희망" in flat or "밴드" in flat) and "~" in flat:
                    for row in t["rows"]:
                        first_cells = " ".join(row[:2]) if len(row) >= 2 else " ".join(row)
                        joined = " ".join(row)
                        if ("희망" in first_cells or "밴드" in first_cells) and "~" in joined:
                            prices = re.findall(r'([\d,]+)\s*원', joined)
                            if len(prices) < 2:
                                prices_match = re.findall(r'([\d,]+)\s*~\s*([\d,]+)', joined)
                                if prices_match:
                                    prices = list(prices_match[0])
                            if len(prices) >= 2:
                                vals = [parse_number(p) for p in prices]
                                vals = [v for v in vals if v and 100 < v < 1000000]
                                if len(vals) >= 2:
                                    self.data["공모가밴드_하단"] = min(vals[:2])
                                    self.data["공모가밴드_상단"] = max(vals[:2])
                                    self.data["공모가밴드_중간값"] = (self.data["공모가밴드_하단"] + self.data["공모가밴드_상단"]) / 2
                    if "공모가밴드_하단" in self.data:
                        break

    def _extract_confirmed_price(self):
        """확정공모가"""
        if "확정공모가" in self.data and self.data["확정공모가"]:
            return

        candidates = find_tables_with_keywords(
            self.tables,
            ["확정공모가", "확정 공모가"]
        )

        for t, score in candidates:
            for row in t["rows"]:
                joined = " ".join(row)
                if "확정공모가" in joined and "원" in joined:
                    match = re.search(r'([\d,]+)\s*원', joined)
                    if match:
                        val = parse_number(match.group(1))
                        if val and val > 100:
                            self.data["확정공모가"] = val
                            return

    def _extract_shares(self):
        """공모주식수, 신주, 구주 추출
        1순위: 주당 평가가액 산출 내역 테이블 (공모주식수/신주모집/구주매출 정확히 기재)
        2순위: 인수인 테이블에서 인수수량 합산
        """
        # 1순위: 주당 평가가액 산출 내역 테이블 (뒤에서부터 = 정정 후)
        for t in reversed(self.tables):
            flat = " ".join(" ".join(r) for r in t["rows"])
            if "공모주식수" in flat and ("신주모집" in flat or "공모 후" in flat):
                for row in t["rows"]:
                    joined = " ".join(row)
                    # 공모주식수
                    if "공모주식수" in joined and "신주" not in joined and "구주" not in joined:
                        nums = [parse_number(c) for c in row if parse_number(c) and 1000 < parse_number(c) < 500000000]
                        if nums:
                            self.data["공모주식수"] = nums[0]
                    # 신주모집주식수
                    if "신주모집" in joined:
                        nums = [parse_number(c) for c in row if parse_number(c) and 1000 < parse_number(c) < 500000000]
                        if nums:
                            self.data["신주"] = nums[0]
                        elif "-" in joined:
                            self.data["신주"] = 0
                    # 구주매출주식수
                    if "구주매출" in joined:
                        nums = [parse_number(c) for c in row if parse_number(c) and 1000 < parse_number(c) < 500000000]
                        if nums:
                            self.data["구주"] = nums[0]
                        elif "-" in joined:
                            self.data["구주"] = 0
                    # 상장후주식수 (공모 후 발행주식수)도 여기서 가져오기
                    if "공모 후 발행" in joined or "공모후 발행" in joined:
                        nums = [parse_number(c) for c in row if parse_number(c) and 100000 < parse_number(c) < 500000000]
                        if nums:
                            self.data["상장후주식수"] = nums[0]

                if "공모주식수" in self.data:
                    break

        # 2순위: 인수인 테이블에서 인수수량 합산
        if "공모주식수" not in self.data:
            candidates = find_tables_with_keywords(
                self.tables,
                ["인수인", "인수수량", "인수금액", "인수방법"]
            )
            for t, score in reversed(candidates):
                if score < 3:
                    continue
                total_shares = 0
                for row in t["rows"]:
                    joined = " ".join(row)
                    if any(kw in joined for kw in ["대표", "주관", "인수회사"]):
                        nums = [parse_number(c) for c in row if parse_number(c)]
                        valid = [n for n in nums if 100000 < n < 100000000]
                        if valid:
                            total_shares += min(valid)
                if total_shares > 0:
                    self.data["공모주식수"] = total_shares
                    break

        # 기본값 설정
        if "구주" not in self.data:
            self.data["구주"] = 0
        if "신주" not in self.data and "공모주식수" in self.data:
            self.data["신주"] = self.data["공모주식수"] - self.data.get("구주", 0)

        # 검증
        if self.data.get("구주", 0) > self.data.get("공모주식수", 0):
            self.data["구주"] = 0
            self.data["신주"] = self.data.get("공모주식수", 0)
        if self.data.get("신주", 0) < 0:
            self.data["구주"] = 0
            self.data["신주"] = self.data.get("공모주식수", 0)

        # 상장후 주식수 - 1순위: 밸류에이션 테이블의 주식수 (가장 정확)
        val_candidates = find_tables_with_keywords(
            self.tables,
            ["평가모형", "적용산식", "주식수", "평가가액"]
        )
        for t, score in val_candidates:
            if score < 2:
                continue
            for row in t["rows"]:
                joined = " ".join(row)
                # ③ 주식수 / ④ 주식수 / ⑤ 적용 주식수 / ⑥ 적용 주식수
                if "주식수" in joined and any(c in joined for c in ["③", "④", "⑤", "⑥"]):
                    # "13,489,530주" 또는 "13,489,530(주)" 또는 별도 셀
                    match = re.search(r'([\d,]+)\s*[\(]?주', joined)
                    if match:
                        val = parse_number(match.group(1))
                        if val and 100000 < val < 500000000:  # 10만~5억주
                            self.data["상장후주식수"] = val
                            break
                    # 별도 셀: ['주', '13,489,530']
                    for idx, cell in enumerate(row):
                        if cell.strip() == "주" and idx + 1 < len(row):
                            num = parse_number(row[idx + 1])
                            if num and 100000 < num < 500000000:
                                self.data["상장후주식수"] = num
                                break
            if "상장후주식수" in self.data:
                break

        # 2순위: 총발행주식수 테이블 (상한 500000000 체크)
        if "상장후주식수" not in self.data:
            candidates = find_tables_with_keywords(
                self.tables,
                ["총발행주식수", "공모후 총발행주식", "상장후 발행주식"]
            )
            for t, score in candidates:
                for row in t["rows"]:
                    joined = " ".join(row)
                    if "총발행주식수" in joined:
                        match = re.search(r'([\d,]+)주', joined)
                        if match:
                            val = parse_number(match.group(1))
                            if val and 100000 < val < 500000000:
                                self.data["상장후주식수"] = val
                                break
                if "상장후주식수" in self.data:
                    break

        # 3순위: 합계 행
        if "상장후주식수" not in self.data:
            candidates = find_tables_with_keywords(
                self.tables,
                ["공모 신주발행주식수", "합계"]
            )
            for t, score in reversed(candidates):
                for row in t["rows"]:
                    if "합계" in " ".join(row):
                        for cell in row:
                            num = parse_number(cell)
                            if num and 100000 < num < 500000000:
                                self.data["상장후주식수"] = num
                                break
                if "상장후주식수" in self.data:
                    break

    def _extract_float(self):
        """유통가능주식수"""
        candidates = find_tables_with_keywords(
            self.tables,
            ["유통가능", "상장일 유통"]
        )

        for t, score in candidates:
            for row in t["rows"]:
                joined = " ".join(row)
                if "상장일" in joined and "유통" in joined:
                    nums = [parse_number(c) for c in row if parse_number(c)]
                    pcts = [parse_percentage(c) for c in row if parse_percentage(c)]
                    if nums:
                        self.data["유통가능주식수"] = max(nums)
                    if pcts:
                        self.data["유통가능주식수비율"] = pcts[0]
                    return

    def _extract_fees(self):
        """인수수수료 총액 + 수수료율
        1순위: 발행제비용 테이블 (구분/금액/계산근거)
        2순위: 인수대가 전용 테이블 (대가수령자/금액)
        3순위: 인수인 테이블의 인수대가 칼럼
        """
        # 1순위: 발행제비용 테이블에서 인수수수료 행 (뒤에서부터 = 정정 후 우선)
        for t in reversed(self.tables):
            flat = " ".join(" ".join(r) for r in t["rows"])
            # 발행제비용 테이블: 인수수수료 + (등록세 or 상장수수료) + 헤더에 "구분"+"금액"
            header_check = " ".join(" ".join(r) for r in t["rows"][:2])
            has_header = ("구분" in header_check or "구 분" in header_check) and ("금액" in header_check or "금 액" in header_check)
            if "인수수수료" in flat and ("등록세" in flat or "상장수수료" in flat or "상장심사" in flat) and has_header and len(t["rows"]) >= 4:
                # 단위 판단: 명시적 텍스트 또는 합계 크기로 추정
                unit_multiplier = 1  # 기본 원
                if "백만원" in flat:
                    unit_multiplier = 1000000
                elif "천원" in flat:
                    unit_multiplier = 1000
                else:
                    # 합계 행의 크기로 단위 추정
                    for row in t["rows"]:
                        if "합계" in " ".join(row) or "합 계" in " ".join(row):
                            for cell in row:
                                num = parse_number(cell)
                                if num and num > 10:
                                    # 합계 기준: 발행제비용 합계는 보통 5억~100억원
                                    # 백만원 단위: 합계 500~100,000 (5억~1000억)
                                    # 천원 단위: 합계 500,000~100,000,000 (5억~1000억)
                                    # 원 단위: 합계 500,000,000 이상 (5억~)
                                    if num < 100000:  # 10만 미만 → 백만원 단위
                                        unit_multiplier = 1000000
                                    elif num < 100000000:  # 1억 미만 → 천원 단위
                                        unit_multiplier = 1000
                                    # 1억 이상 → 원 단위
                                    break
                            break

                for row in t["rows"]:
                    joined = " ".join(row)
                    if "인수수수료" in joined and "성과" not in joined:
                        for cell in row:
                            num = parse_number(cell)
                            if num and num > 10:
                                fee_won = num * unit_multiplier  # 원 단위로 변환
                                if 10000000 < fee_won < 50000000000:  # 1천만~500억
                                    self.data["인수수수료총액"] = fee_won
                                    self.data["인수수수료총액_억원"] = round(fee_won / 100000000, 2)
                                    break
                        # 수수료율
                        for cell in row:
                            match = re.search(r'(\d+\.?\d*)\s*%', cell)
                            if match:
                                self.data["인수수수료율"] = float(match.group(1))
                                break
                        if "인수수수료총액" in self.data:
                            return

        # 2순위: 인수대가 전용 테이블 (대가수령자/금액/금액산정내역)
        candidates = find_tables_with_keywords(
            self.tables,
            ["인수수수료", "대가수령자", "금액산정내역"]
        )
        total_fee = 0
        for t, score in reversed(candidates):
            if score < 2:
                continue
            in_fee_section = False
            for row in t["rows"]:
                joined = " ".join(row)
                if "인수수수료" in joined:
                    if joined.strip().startswith("성과수수료"):
                        in_fee_section = False
                        continue
                    in_fee_section = True
                    for cell in row:
                        num = parse_number(cell)
                        if num and 100000000 < num < 50000000000:
                            total_fee += num
                    # 수수료율
                    for cell in row:
                        match = re.search(r'(\d+\.?\d*)\s*%', cell)
                        if match:
                            self.data["인수수수료율"] = float(match.group(1))
                    continue
                if any(kw in joined for kw in ["성과수수료", "대표주관수수료"]):
                    in_fee_section = False
                    continue
                if in_fee_section and any(kw in joined for kw in ["증권", "금융투자"]):
                    for cell in row:
                        num = parse_number(cell)
                        if num and 100000000 < num < 50000000000:
                            total_fee += num
            if total_fee > 0:
                self.data["인수수수료총액"] = total_fee
                self.data["인수수수료총액_억원"] = round(total_fee / 100000000, 2)
                return

        # 3순위: 인수인 테이블의 인수대가 칼럼
        if self.data.get("_인수대가합계"):
            fee = self.data["_인수대가합계"]
            if 0 < fee < 50000000000:
                self.data["인수수수료총액"] = fee
                self.data["인수수수료총액_억원"] = round(fee / 100000000, 2)

    def _extract_listing_type(self):
        """상장유형 판단
        - '적용 재무수치' 필드에서 추정치/실적치 판단
        - 추정치 → 기술특례 (단, 연환산은 일반기업)
        - 실적치/연환산 → 일반기업
        """
        candidates = find_tables_with_keywords(
            self.tables,
            ["적용 재무수치", "적용산식", "평가모형"]
        )

        for t, score in candidates:
            if score < 2:
                continue
            for row in t["rows"]:
                joined = " ".join(row)
                if "적용 재무수치" in joined or "적용재무수치" in joined:
                    # 연환산 = 일반기업 (IPO 시장에서는 추정치가 아님)
                    if "연환산" in joined or "LTM" in joined:
                        self.data["상장유형"] = "일반기업"
                    elif "실적" in joined:
                        self.data["상장유형"] = "일반기업"
                    elif "추정" in joined:
                        self.data["상장유형"] = "기술특례"
                    return

        # 대안: 적용이익에 "추정" 키워드
        for t, score in find_tables_with_keywords(self.tables, ["추정당기순이익", "추정 당기순이익", "추정매출"]):
            self.data["상장유형"] = "기술특례"
            return

        self.data["상장유형"] = None

    def _detect_spac_merger(self):
        """스팩합병상장 감지"""
        if self.data.get("평가모형"):
            return
        # 앞쪽 50개 테이블에서 검색
        front_text = " ".join(t["flat"] for t in self.tables[:50])
        spac_kws = ["합병의 개요", "합병에 관한", "기업인수목적", "합병비율", "합병법인"]
        if any(kw in front_text for kw in spac_kws):
            self.data["평가모형"] = "스팩합병상장"
            self.data["상장유형"] = "스팩합병"

    def _calculate_derived(self):
        """파생 필드 계산"""
        mult = self.data.get("적용멀티플")
        earnings = self.data.get("적용이익_백만원")
        model = self.data.get("평가모형", "")

        # 평가모형이 없지만 멀티플이 있으면, 멀티플 크기로 유추
        if not model and mult:
            if mult > 5:
                self.data["평가모형"] = "PER"  # PER은 보통 10~50배
            elif mult < 5:
                self.data["평가모형"] = "PBR"  # PBR은 보통 0.5~5배
            model = self.data.get("평가모형", "")

        # 적정시가총액
        if mult and earnings:
            if "EV" in model or "EBITDA" in model:
                # EV/EBITDA: EV = 멀티플 × EBITDA, 적정시총 = EV - 순차입금 - 비지배지분 + 공모유입자금
                ev = mult * earnings
                net_debt = self.data.get("_순차입금_백만원", 0) or 0
                minority = self.data.get("_비지배지분_백만원", 0) or 0
                ipo_funds = self.data.get("_공모유입자금_백만원", 0) or 0
                equity_value = ev - net_debt - minority + ipo_funds
                self.data["적정시가총액_백만원"] = round(equity_value)
                self.data["적정시가총액_억원"] = round(equity_value / 100, 2)
            else:
                # PER/PSR/PBR: 멀티플 × 적용이익
                self.data["적정시가총액_백만원"] = round(mult * earnings)
                self.data["적정시가총액_억원"] = round(mult * earnings / 100, 2)

        # 기준시가총액 = 확정공모가 × 상장후주식수
        price = self.data.get("확정공모가")
        shares = self.data.get("상장후주식수")
        if price and shares:
            self.data["기준시가총액_억원"] = round(price * shares / 100000000, 2)

        # 확정공모금액 = 확정공모가 × 공모주식수(신주+구주)
        ipo_shares = self.data.get("공모주식수")
        if price and ipo_shares:
            self.data["확정공모금액_억원"] = round(price * ipo_shares / 100000000, 2)

        # 공모비율 = 공모주식수 / 상장후주식수
        if ipo_shares and shares:
            self.data["공모비율"] = round(ipo_shares / shares * 100, 2)

        # 상단대비 확정가비율
        band_top = self.data.get("공모가밴드_상단")
        if price and band_top:
            self.data["상단대비확정가비율"] = round(price / band_top * 100, 2)

        # 공모가 최종 위치
        band_low = self.data.get("공모가밴드_하단")
        if price and band_low and band_top:
            if price > band_top:
                self.data["공모가최종"] = "상단초과"
            elif price == band_top:
                self.data["공모가최종"] = "상단"
            elif price == band_low:
                self.data["공모가최종"] = "하단"
            elif price < band_low:
                self.data["공모가최종"] = "하단미만"
            else:
                self.data["공모가최종"] = "밴드내"


def extract_ipo_data(filepath):
    """파일 경로로부터 IPO 데이터 추출 (인코딩 자동 감지)"""
    with open(filepath, "rb") as f:
        raw = f.read()

    # UTF-8 먼저 시도, 실패하면 CP949/EUC-KR
    content = None
    for enc in ["utf-8", "cp949", "euc-kr"]:
        try:
            decoded = raw.decode(enc)
            # 한글 키워드가 정상 디코딩되는지 확인
            if any(kw in decoded for kw in ["평가", "공모", "인수", "상장", "증권"]):
                content = decoded
                break
        except (UnicodeDecodeError, LookupError):
            continue
    if content is None:
        # 최후 수단: errors=replace
        content = raw.decode("utf-8", errors="replace")

    extractor = IPOExtractor(content)
    return extractor.extract_all()


# ========== 테스트 ==========
if __name__ == "__main__":
    import json

    doc_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "poc_docs", "리브스메드", "20251212000519.xml"
    )

    print("리브스메드 투자설명서 데이터 추출 중...")
    data = extract_ipo_data(doc_path)

    print("\n" + "=" * 60)
    print("추출 결과")
    print("=" * 60)

    # 칼럼 순서대로 출력
    columns = [
        ("대표주관회사", "대표주관회사"),
        ("인수단", "인수단"),
        ("상장유형", "상장유형"),
        ("시장구분", "시장구분"),
        ("평가방법", "평가모형"),
        ("적용멀티플", "적용멀티플"),
        ("적용이익 (백만원)", "적용이익_백만원"),
        ("적정시가총액 (억원)", "적정시가총액_억원"),
        ("할인율 하단", "할인율_하단"),
        ("할인율 상단", "할인율_상단"),
        ("공모가밴드 중간값", "공모가밴드_중간값"),
        ("공모가밴드 하단", "공모가밴드_하단"),
        ("공모가밴드 상단", "공모가밴드_상단"),
        ("확정공모가 (원)", "확정공모가"),
        ("상단대비 확정가비율 (%)", "상단대비확정가비율"),
        ("공모가 최종", "공모가최종"),
        ("기준시가총액 (억원)", "기준시가총액_억원"),
        ("확정공모금액 (억원)", "확정공모금액_억원"),
        ("주당 평가가액 (원)", "주당평가가액"),
        ("공모비율 (%)", "공모비율"),
        ("상장후 주식수", "상장후주식수"),
        ("유통가능주식수", "유통가능주식수"),
        ("유통가능주식수 비율 (%)", "유통가능주식수비율"),
        ("공모주식수", "공모주식수"),
        ("신주", "신주"),
        ("구주", "구주"),
        ("인수수수료 총액 (억원)", "인수수수료총액_억원"),
    ]

    for label, key in columns:
        value = data.get(key, "❌ 미추출")
        if isinstance(value, float):
            value = f"{value:,.2f}"
        elif isinstance(value, int):
            value = f"{value:,}"
        print(f"  {label:30s} │ {value}")

    # 전체 데이터 JSON 저장
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poc_result.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n전체 데이터 → {output_path}")
