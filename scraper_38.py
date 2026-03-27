"""
38커뮤니케이션에서 수요예측/청약 데이터 크롤링
- 기관경쟁률, 의무보유확약 비율: o=r1 (수요예측 결과 리스트) 일괄 수집
- 청약경쟁률(비례): 개별 상세 페이지에서 수집
- 수요예측_참여기관수: 개별 상세 페이지에서 수집 (가능한 경우)
"""

import requests
from bs4 import BeautifulSoup
import re
import time


def _fix_competition_rate(raw):
    """경쟁률 문자열을 float로 변환. '799,76' 같은 콤마-소수점 오타도 처리."""
    # 콤마가 하나이고 뒤가 2자리 이하면 소수점 오타로 판단 (e.g. "799,76")
    if re.match(r"^\d+,\d{1,2}$", raw):
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def get_38_demand_forecast_results(pages=55):
    """38커뮤니케이션 수요예측 결과(o=r1) 리스트에서 기관경쟁률/의무보유확약 일괄 수집.

    Returns: dict {회사명: {기관경쟁률: float, 의무보유확약비율: float}}
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    results = {}
    for page in range(1, pages + 1):
        try:
            resp = session.get(
                "http://www.38.co.kr/html/fund/index.htm",
                params={"o": "r1", "page": str(page)},
                timeout=10,
            )
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "lxml")

            found_any = False
            for table in soup.find_all("table"):
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if len(cells) < 6:
                        continue
                    # Header row: 기업명, 예측일, 공모희망가, 공모가, 공모금액, 기관경쟁률, 의무보유확약, 주간사
                    if cells[0] == "기업명":
                        continue

                    name = cells[0].strip()
                    # Remove suffixes like (유가), (코스닥) for matching
                    name_clean = re.sub(r"\s*\(유가\)\s*$", "", name)
                    name_clean = re.sub(r"\s*\(코스닥\)\s*$", "", name_clean)

                    if not name_clean or len(name_clean) < 2:
                        continue

                    data = {}

                    # 기관경쟁률: "1328.82:1"
                    if len(cells) > 5 and cells[5]:
                        match = re.search(r"([\d,.]+)\s*:\s*1", cells[5])
                        if match:
                            val = match.group(1).replace(",", "")
                            try:
                                data["기관경쟁률"] = float(val)
                            except ValueError:
                                pass

                    # 의무보유확약: "43.06%"
                    if len(cells) > 6 and cells[6]:
                        match = re.search(r"([\d.]+)\s*%", cells[6])
                        if match:
                            try:
                                data["의무보유확약비율"] = float(match.group(1))
                            except ValueError:
                                pass

                    if data:
                        # Store both clean name and original (with suffix)
                        results[name_clean] = data
                        if name != name_clean:
                            results[name] = data
                        found_any = True

            if not found_any and page > 5:
                # No more data
                break

        except Exception as e:
            print(f"  Page {page} error: {e}")

        time.sleep(0.3)

    return results


def get_38_company_list(pages=55):
    """38커뮤니케이션 IPO 목록(o=k)에서 회사명 → 상세 페이지 번호 매핑"""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    companies = {}
    for page in range(1, pages + 1):
        try:
            resp = session.get(
                "http://www.38.co.kr/html/fund/index.htm",
                params={"o": "k", "page": str(page)},
                timeout=10,
            )
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "lxml")

            found_any = False
            for a in soup.find_all("a"):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "/html/fund/" in href and "o=v" in href and "no=" in href and text and len(text) > 1:
                    match = re.search(r"no=(\d+)", href)
                    if match:
                        no = int(match.group(1))
                        # Only real company pages have small no values (< 10000)
                        if no < 10000:
                            # Clean name: remove (유가), (코스닥) suffix
                            name_clean = re.sub(r"\s*\(유가\)\s*$", "", text)
                            name_clean = re.sub(r"\s*\(코스닥\)\s*$", "", name_clean)
                            companies[name_clean] = no
                            if text != name_clean:
                                companies[text] = no
                            found_any = True

            if not found_any and page > 5:
                break

        except Exception as e:
            print(f"  Page {page} error: {e}")

        time.sleep(0.3)

    return companies


def get_38_detail(no):
    """38커뮤니케이션 상세 페이지에서 수요예측/청약 데이터 추출"""
    resp = requests.get(
        f"http://www.38.co.kr/html/fund/index.htm?o=v&no={no}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    resp.encoding = "euc-kr"
    soup = BeautifulSoup(resp.text, "lxml")

    data = {}

    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)

        for row in rows:
            joined = " ".join(row)

            # 기관경쟁률: "기관경쟁률 231.87:1"
            if "기관경쟁률" in joined:
                match = re.search(r"기관경쟁률\s*([\d,.]+)\s*:\s*1", joined)
                if match:
                    val = match.group(1).replace(",", "")
                    try:
                        data["기관경쟁률"] = float(val)
                    except ValueError:
                        pass

            # 의무보유확약: "의무보유확약 17.12%"
            if "의무보유확약" in joined:
                match = re.search(r"의무보유확약\s*([\d.]+)\s*%", joined)
                if match:
                    data["의무보유확약비율"] = float(match.group(1))

            # 청약경쟁률: "청약경쟁률 390:1 (비례 780:1)"
            # 주의: 38커뮤니케이션에서 "799,76:1" 같이 소수점을 콤마로 오기하는 케이스 있음
            if "청약경쟁률" in joined:
                # 비례 경쟁률 우선
                match_prop = re.search(r"비례\s*([\d,.]+)\s*:\s*1", joined)
                if match_prop:
                    val = _fix_competition_rate(match_prop.group(1))
                    if val is not None:
                        data["청약경쟁률_비례"] = val

                # 전체 경쟁률
                match_total = re.search(r"청약경쟁률\s*([\d,.]+)\s*:\s*1", joined)
                if match_total:
                    val = _fix_competition_rate(match_total.group(1))
                    if val is not None:
                        data["청약경쟁률"] = val

            # 수요예측 참여기관수: look for "참여건수" or "참여기관" patterns
            if "참여" in joined and ("건수" in joined or "기관" in joined):
                match = re.search(r"참여[기관건수\s]*([\d,]+)\s*[건개사]", joined)
                if match:
                    val = match.group(1).replace(",", "")
                    try:
                        data["수요예측_참여기관수"] = int(val)
                    except ValueError:
                        pass

    # Fallback: pre-2022 IPOs have no 비례/균등 split, only total 청약경쟁률
    if "청약경쟁률" in data and "청약경쟁률_비례" not in data:
        data["청약경쟁률_비례"] = data["청약경쟁률"]

    return data


def _build_name_lookup(source_names):
    """38커뮤니케이션 이름에서 DB 매칭용 lookup 구축.

    38커뮤니케이션은 '더핑크퐁컴퍼니(구.스마트스터디)' 같은 형식을 쓰므로
    '더핑크퐁컴퍼니' → 원래 키로 매핑하는 reverse lookup 생성.
    """
    lookup = {}
    for name in source_names:
        lookup[name] = name
        # '더핑크퐁컴퍼니(구.스마트스터디)' → '더핑크퐁컴퍼니'
        m = re.match(r"^(.+?)\(구\.", name)
        if m:
            lookup[m.group(1)] = name
        # Remove (유가), (코스닥)
        clean = re.sub(r"\s*\((유가|코스닥)\)\s*$", "", name)
        if clean != name:
            lookup[clean] = name
    return lookup


def update_db_with_38_data(db_path="ipo_data.db"):
    """DB의 모든 completed 회사에 대해 38커뮤니케이션 데이터 업데이트.

    Phase 1: o=r1 리스트에서 기관경쟁률/의무보유확약 일괄 수집 (빠름)
    Phase 2: 개별 상세 페이지에서 청약경쟁률 수집 (기관경쟁률 없는 건도 보완)
    """
    import sqlite3

    conn = sqlite3.connect(db_path, timeout=30)

    # DB 회사 목록
    companies_db = conn.execute(
        "SELECT 회사명, 기관경쟁률, 청약경쟁률_비례 FROM ipo_companies WHERE 처리상태='completed'"
    ).fetchall()
    company_names = [r[0] for r in companies_db]
    existing_inst = {r[0] for r in companies_db if r[1] is not None}
    existing_sub = {r[0] for r in companies_db if r[2] is not None}

    print(f"DB 회사: {len(company_names)}개 (기관경쟁률 {len(existing_inst)}개, 청약경쟁률 {len(existing_sub)}개)")

    # ── Phase 1: 수요예측 결과 리스트 (o=r1) ──
    print("\n[Phase 1] 수요예측 결과 리스트 수집 중 (o=r1, ~55 pages)...")
    demand_results = get_38_demand_forecast_results(pages=55)
    print(f"  수집: {len(demand_results)}개 기업")

    # Build fuzzy lookup for demand results
    demand_lookup = _build_name_lookup(demand_results.keys())

    phase1_success = 0
    for name in company_names:
        # Try exact match first, then fuzzy
        matched_key = None
        if name in demand_results:
            matched_key = name
        elif name in demand_lookup:
            matched_key = demand_lookup[name]

        if matched_key:
            data = demand_results[matched_key]
            sets = []
            params = []
            for field in ["기관경쟁률", "의무보유확약비율"]:
                if field in data:
                    sets.append(f"{field} = ?")
                    params.append(data[field])

            if sets:
                # Only update if currently NULL (don't overwrite existing data)
                conditions = " OR ".join([f"{f.split(' = ')[0]} IS NULL" for f in sets])
                params.append(name)
                conn.execute(
                    f"UPDATE ipo_companies SET {', '.join(sets)} WHERE 회사명 = ? AND ({conditions})",
                    params,
                )
                phase1_success += 1

    conn.commit()
    print(f"  Phase 1 매칭: {phase1_success}개 업데이트")

    # Check new counts after phase 1
    inst_after_p1 = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 기관경쟁률 IS NOT NULL").fetchone()[0]
    print(f"  기관경쟁률: {inst_after_p1}/{len(company_names)}")

    # ── Phase 2: 상세 페이지에서 청약경쟁률 수집 ──
    print("\n[Phase 2] 상세 페이지 목록 수집 중 (o=k, ~55 pages)...")
    company_map = get_38_company_list(pages=55)
    print(f"  수집: {len(company_map)}개 상세 페이지 링크")

    # Build fuzzy lookup for company_map
    company_map_lookup = _build_name_lookup(company_map.keys())

    # Only fetch detail for companies missing 청약경쟁률 OR 기관경쟁률
    # Re-check what's still missing after Phase 1
    still_missing = conn.execute(
        "SELECT 회사명 FROM ipo_companies WHERE 처리상태='completed' AND (청약경쟁률_비례 IS NULL OR 기관경쟁률 IS NULL)"
    ).fetchall()
    need_detail = {r[0] for r in still_missing}

    phase2_success = 0
    phase2_skip = 0
    total_to_check = sum(1 for name in need_detail if name in company_map or name in company_map_lookup)
    print(f"  상세 페이지 수집 대상: {total_to_check}개")

    for i, name in enumerate(need_detail):
        # Fuzzy match
        matched_key = None
        if name in company_map:
            matched_key = name
        elif name in company_map_lookup:
            matched_key = company_map_lookup[name]
        if matched_key is None:
            continue

        no = company_map[matched_key]
        try:
            data = get_38_detail(no)
        except Exception as e:
            print(f"  {name}: 에러 {e}")
            continue

        if data:
            sets = []
            params = []
            for field in ["기관경쟁률", "의무보유확약비율", "청약경쟁률_비례", "수요예측_참여기관수"]:
                if field in data:
                    sets.append(f"{field} = COALESCE({field}, ?)")
                    params.append(data[field])

            if sets:
                params.append(name)
                # Use COALESCE to not overwrite existing data
                set_strs = []
                p = []
                for field in ["기관경쟁률", "의무보유확약비율", "청약경쟁률_비례", "수요예측_참여기관수"]:
                    if field in data:
                        set_strs.append(f"{field} = CASE WHEN {field} IS NULL THEN ? ELSE {field} END")
                        p.append(data[field])
                p.append(name)
                conn.execute(
                    f"UPDATE ipo_companies SET {', '.join(set_strs)} WHERE 회사명 = ?",
                    p,
                )
                phase2_success += 1
                if (phase2_success % 50) == 0:
                    print(f"  진행: {phase2_success}/{total_to_check}")
                    conn.commit()
        else:
            phase2_skip += 1

        time.sleep(0.3)

    conn.commit()

    # Final counts
    total = conn.execute("SELECT COUNT(*) FROM ipo_companies").fetchone()[0]
    inst_final = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 기관경쟁률 IS NOT NULL").fetchone()[0]
    sub_final = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 청약경쟁률_비례 IS NOT NULL").fetchone()[0]
    conf_final = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 의무보유확약비율 IS NOT NULL").fetchone()[0]

    # Check if 수요예측_참여기관수 column exists
    try:
        part_final = conn.execute("SELECT COUNT(*) FROM ipo_companies WHERE 수요예측_참여기관수 IS NOT NULL").fetchone()[0]
    except Exception:
        part_final = 0

    conn.close()

    print(f"\n{'='*50}")
    print(f"최종 결과 (전체 {total}개):")
    print(f"  기관경쟁률:      {inst_final}/{total} ({100*inst_final//total}%)")
    print(f"  의무보유확약비율: {conf_final}/{total} ({100*conf_final//total}%)")
    print(f"  청약경쟁률_비례: {sub_final}/{total} ({100*sub_final//total}%)")
    print(f"  수요예측_참여기관수: {part_final}/{total} ({100*part_final//total}%)")
    print(f"  Phase 2: 성공 {phase2_success}, 스킵 {phase2_skip}")


if __name__ == "__main__":
    update_db_with_38_data()
