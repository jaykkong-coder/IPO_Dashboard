"""
유통가능주식수비율 결정적 재검증 추출기.

DART 투자설명서/증권신고서 원문 캐시(docs/<회사명>/<rcept_no>.xml)에서
"상장 직후 유통가능주식수(비율)" 값을 파싱한다. 1차 검증(45건) 리포트
(.superpowers/sdd/verify-float-report.md)에서 확인된 파서 버그 패턴을
전부 회피하도록 설계했다:

  ① 매각제한/유통제한/의무보유 비율을 유통가능비율로 오채택하는 것을 방지
     -> "유통가능" 키워드에 인접한 숫자만 후보로 채택하고, 후보-키워드
        사이 구간에 "의무보유/제한/의무예탁/예탁일" 이 끼어 있으면 버린다.
  ② [기간별/시점별 유통가능 주식수] 표에서 미래 시점(개월/년 후, 100%)을
     상장 직후 값으로 오채택하는 것을 방지
     -> 표에서는 "상장일/상장직후/특정일자" 같은 "N개월/N년 뒤"가 아닌
        행만 채택하고, 100%에 근접한 값은 전부 버린다.
  ③ 상장후주식수 필드 자체의 오염으로 인한 재계산 불일치(false positive)
     -> DB "상장후주식수" 재계산에만 의존하지 않고, 원문 내에서 직접
        "상장예정주식수 N주" 같은 총수를 찾아 자체 검증(local_total)을
        1순위로 사용한다. 표는 같은 표의 "합계" 행을 total로 쓴다.
  ④ 정정신고서의 "정정 전" 구 수치 채택 방지
     -> "정정 전/정정 후" 마커를 추적해 정정 전 구간의 후보는 배제한다.

검증 로직: 추출한 (유통가능주식수 ÷ 총주식수) 재계산이 추출한 비율과
±1%p 이내로 맞을 때만 'confident'. 그 외 'ambiguous'.

사용법:
  python3 verify_float_extractor.py --calibrate   # data_corrections 45건 대조
  (전수 실행/DB 반영은 별도 드라이버에서 이 모듈을 import해서 수행)
"""

import argparse
import os
import re
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ipo_data.db')
DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs')

UNIVERSE_SQL = '''
    SELECT 회사명, dart_corp_code, dart_rcept_no, 상장후주식수, 유통가능주식수비율
    FROM ipo_companies
    WHERE "상장일" >= '2024-01-01'
      AND ("상장유형" IS NULL OR "상장유형" != 'SPAC')
      AND "확정공모가" IS NOT NULL
    ORDER BY 회사명
'''

# ---------------------------------------------------------------------------
# 원문 HTML/SGML 파싱 유틸
# ---------------------------------------------------------------------------

TAG_RE = re.compile(r'<[^>]+>')
DIGIT_GAP_RE = re.compile(r'(?<=\d)\s+(?=\d)')  # DART가 <SPAN>을 임의 위치에서
# 줄바꿈으로 쪼개면서 숫자 중간에 개행이 들어가는 경우가 흔하다. 예:
# "3,582,\n159주" / "3\n7.48%" -> 숫자 사이 공백/개행을 제거해 원복한다.
WS_RE = re.compile(r'\s+')
TR_RE = re.compile(r'<TR\b[^>]*>(.*?)</TR>', re.S | re.I)
CELL_RE = re.compile(r'<T[DH]\b([^>]*)>(.*?)</T[DH]>', re.S | re.I)
ROWSPAN_RE = re.compile(r'ROWSPAN\s*=\s*"?(\d+)"?', re.I)
PERIOD_RE = re.compile(r'\d+\s*(?:개월|년)(?:\s*\d+\s*개월)?\s*(?:뒤|후)')
PCT_RE = re.compile(r'(\d{1,3}(?:\.\d{1,3})?)\s*%')
QTY_TOKEN_RE = re.compile(r'^[\d,]+$')


def normalize_cell(raw):
    txt = TAG_RE.sub('', raw)
    txt = DIGIT_GAP_RE.sub('', txt)
    txt = WS_RE.sub(' ', txt).strip()
    return txt


def extract_rows(text):
    """<TR>...</TR> 블록을 (위치, [셀텍스트...], 첫셀 ROWSPAN) 리스트로."""
    rows = []
    for trm in TR_RE.finditer(text):
        block = trm.group(1)
        raw_cells = CELL_RE.findall(block)
        cells = [normalize_cell(c[1]) for c in raw_cells]
        first_rowspan = 1
        if raw_cells:
            m = ROWSPAN_RE.search(raw_cells[0][0])
            if m:
                first_rowspan = int(m.group(1))
        if cells:
            rows.append((trm.start(), cells, first_rowspan))
    return rows


def qty_from_cell(c):
    token = c.replace('주', '').strip()
    if QTY_TOKEN_RE.fullmatch(token):
        digits = token.replace(',', '')
        if digits.isdigit() and len(digits) >= 3:
            return int(digits)
    return None


def row_qty_pct_pairs(cells):
    """행의 셀들을 순회하며 (직전 주식수, %) 쌍을 만든다.

    콜스팬으로 주식수 컬럼 하나에 %(희석전) / %(희석후) 두 컬럼이 붙는
    경우와, 주식수·%가 (공모전, 공모후)처럼 반복되는 경우 모두를
    커버한다 (같은 주식수에 여러 %가 매칭되거나, 여러 주식수-% 쌍이
    번갈아 나오거나).
    """
    pairs = []
    current_qty = None
    for c in cells[1:]:
        if '%' in c:
            m = PCT_RE.search(c)
            if m and current_qty is not None:
                pairs.append((current_qty, float(m.group(1))))
        else:
            q = qty_from_cell(c)
            if q is not None:
                current_qty = q
    return pairs


def find_local_total(text, row_pos, window=4000):
    """같은 표 안에서 뒤따라오는 '합계/총계' 행의 마지막 주식수를 total로."""
    seg = text[row_pos:row_pos + window]
    for _, cells, _ in extract_rows(seg):
        label = cells[0].strip()
        if label in ('합계', '총계') or label.endswith('합계') or label.endswith('총계'):
            nums = [qty_from_cell(c) for c in cells[1:]]
            nums = [n for n in nums if n is not None]
            if nums:
                return nums[-1]
    return None


CORRECTION_MARK_RE = re.compile(r'정정\s*(전|후)')


def correction_tag(text, pos, window=3000):
    """후보 앞쪽 window 안에서 가장 최근 '정정 전'/'정정 후' 마커를 찾는다."""
    seg = text[max(0, pos - window):pos]
    tag = None
    for m in CORRECTION_MARK_RE.finditer(seg):
        tag = 'post' if m.group(1) == '후' else 'pre'
    return tag


AGGREGATE_WORDS = ('소계', '합계', '총계')
SUBTOTAL_WORDS = ('소계',)
GROUP_KEYWORDS = ('유통가능', '유통제한', '매각제한', '의무보유')


def nearest_group_label(all_rows, idx, back_window=3000):
    """ROWSPAN으로 라벨이 한 번만 등장하는 breakdown 표에서, '소계' 행이
    속한 그룹(유통가능물량/유통제한물량 등)의 라벨을 역방향으로 찾는다."""
    pos0 = all_rows[idx][0]
    j = idx - 1
    while j >= 0 and pos0 - all_rows[j][0] <= back_window:
        lbl = all_rows[j][1][0]
        if any(k in lbl for k in GROUP_KEYWORDS):
            return lbl
        j -= 1
    return None


def table_candidates(text):
    """표 기반 후보: [기간별 유통가능 주식수] 류의 '상장일 유통가능' 첫 행,
    또는 가능여부/구분 breakdown 표의 '유통가능물량 소계' 행."""
    cands = []
    all_rows = extract_rows(text)
    for idx, (pos, cells, rowspan0) in enumerate(all_rows):
        label0 = cells[0]
        has_keyword_direct = any(k in label0 for k in GROUP_KEYWORDS)
        is_subtotal_word = label0 in SUBTOTAL_WORDS or any(label0.endswith(w) for w in SUBTOTAL_WORDS)
        if has_keyword_direct:
            effective_label = label0
        elif is_subtotal_word:
            effective_label = nearest_group_label(all_rows, idx) or label0
        else:
            effective_label = label0

        if '유통가능' not in effective_label:
            continue
        if '유통제한' in effective_label or '매각제한' in effective_label or '의무보유' in effective_label:
            continue
        # ROWSPAN>1인 순수 그룹 헤더 행(예: '유통가능물량'만 있는 행)은
        # 그 자체로는 완결된 데이터 행이 아니므로 후보에서 제외한다.
        # (뒤따르는 '소계' 행이 nearest_group_label로 이 라벨을 물려받는다)
        if rowspan0 > 1 and has_keyword_direct and not is_subtotal_word \
                and '합계' not in label0 and '총계' not in label0:
            continue

        is_subtotal = is_subtotal_word or ('합계' in label0) or ('총계' in label0)
        is_period = bool(PERIOD_RE.search(effective_label))
        if is_period and not is_subtotal:
            continue  # 'N개월/N년 뒤 유통가능' 같은 미래 시점 행은 제외

        pairs = row_qty_pct_pairs(cells)
        if not pairs:
            continue
        local_total = find_local_total(text, pos) if is_subtotal else None
        ctag = correction_tag(text, pos)
        for qty, pct in pairs:
            cands.append({
                'pos': pos, 'qty': qty, 'pct': pct,
                'source': 'subtotal_row' if is_subtotal else 'first_row',
                'label': effective_label, 'local_total': local_total,
                'correction_tag': ctag,
            })
    return cands


def plain_text(text):
    t = TAG_RE.sub('', text)
    t = DIGIT_GAP_RE.sub('', t)
    return t


NUM = r'[\d,]{4,}'
PCT = r'\d{1,3}(?:\.\d{1,3})?'
BAD = r'의무보유|제한|의무예탁|예탁일'
GAP = rf'(?:(?!{BAD})[^.]){{0,30}}?'  # '유통가능'까지 가는 동안 매각제한류 단어가
# 끼어 있으면 매칭을 막는다 (①번 버그 방지 핵심 장치)

# qty(pct%) ... 유통가능   예) "2,783,198주(공모 후 상장예정주식수의 29.75%)는 상장 직후 유통가능 물량입니다."
NARR_QTY_PAREN_PCT = re.compile(
    rf'(?P<qty>{NUM})\s*주\s*\([^)]{{0,45}}?(?P<pct>{PCT})\s*%[^)]{{0,15}}?\){GAP}유통\s*가능'
)

# 유통가능주식(인) ... qty주(pct%)   예) "유통가능주식인 3,582,159주(상장 후 17.37%)"
# 주의: "유통가능물량 중 X주(Y%)는 기존주주 보유지분이며 나머지는 공모 물량"처럼
# '중'으로 이어지면 전체가 아니라 하위 항목(부분집합)이므로 명시적으로 배제한다.
NARR_LABEL_THEN_QTY_PAREN = re.compile(
    rf'유통\s*가능\s*(?:주식|물량)(?:(?!중)[^.]){{0,10}}?(?:인|은|는)?\s*'
    rf'(?P<qty>{NUM})\s*주\s*\([^)]{{0,20}}?(?P<pct>{PCT})\s*%'
)

# pct%에 해당하는 qty주 ... 유통가능   예) "55.77%에 해당하는 2,458,326주는 상장 직후 유통가능 물량"
NARR_PCT_THEN_QTY = re.compile(
    rf'약?\s*(?P<pct>{PCT})\s*%\s*(?:에\s*해당하는|에\s*해당|의)?\s*(?P<qty>{NUM})\s*주\s*(?:가|는|이|은)?\s*{GAP}유통\s*가능'
)

# qty주는 ... 유통가능 ... 기준으로 pct%   예) "10,454,535주는 상장 직후 시장에서 유통가능한 물량이며, 상장예정주식수 기준으로 18.02%"
NARR_QTY_THEN_LATER_PCT = re.compile(
    rf'(?P<qty>{NUM})\s*주\s*(?:는|은|가|이)?\s*{GAP}유통\s*가능[^.]{{0,60}}?(?P<pct>{PCT})\s*%'
)

TOTAL_HINT_RE = re.compile(
    rf'(?:상장\s*(?:예정|후)?\s*주식\s*(?:총수|수)|발행\s*주식\s*총수|공모\s*후\s*주식\s*(?:총수|수)|주식\s*총수)'
    rf'[^\d]{{0,20}}?({NUM})\s*주'
)


def find_narrative_total(t, match_start, window=600):
    """후보 앞쪽에서 '상장예정주식수 N주' 류의 총수 힌트를 찾는다.

    DB의 상장후주식수 필드는 오염된 사례가 많아(1차 리포트 Finding ③)
    원문 자체에서 총수를 구해 자체 검증하는 쪽을 우선한다.
    """
    seg = t[max(0, match_start - window):match_start]
    total = None
    for m in TOTAL_HINT_RE.finditer(seg):
        total = int(m.group(1).replace(',', ''))
    return total


def narrative_candidates(text):
    t = plain_text(text)
    cands = []
    for regex, name in [
        (NARR_QTY_PAREN_PCT, 'narr_qty_paren_pct'),
        (NARR_LABEL_THEN_QTY_PAREN, 'narr_label_then_qty_paren'),
        (NARR_PCT_THEN_QTY, 'narr_pct_then_qty'),
        (NARR_QTY_THEN_LATER_PCT, 'narr_qty_then_later_pct'),
    ]:
        for m in regex.finditer(t):
            gd = m.groupdict()
            qty = int(gd['qty'].replace(',', ''))
            pct = float(gd['pct'])
            total = find_narrative_total(t, m.start())
            ctag = correction_tag(t, m.start())
            cands.append({'pos': m.start(), 'qty': qty, 'pct': pct, 'source': name,
                           'label': m.group(0)[:80], 'local_total': total,
                           'correction_tag': ctag})
    return cands


def all_candidates(text):
    return table_candidates(text) + narrative_candidates(text)


def pick_value(cands, db_total, tol=1.0, use_db_fallback=True):
    """후보 목록에서 최종 (verdict, value, detail)을 결정한다.

    1순위: local_total(원문 자체 총수 또는 표의 합계행) 자체검증,
           없으면 DB 상장후주식수 재계산 fallback.
           ±tol(1%p) 이내면 유효(valid) 후보.
    2순위(정정): '정정 전' 태그가 붙은 후보는 '정정 후'/무태그 후보가
           하나라도 있으면 배제한다.
    3순위(출처): 표 기반(subtotal_row/first_row) 후보를 서사문 기반보다
           신뢰 -> 표 후보끼리 일치하면 그것으로 확정.
    4순위(다수결): 총수 검증으로 못 거른 경우, 동일 (주식수,비율) 쌍이
           문서 내 여러 곳(요약+상세 등)에서 반복되는 다수결로 확정한다.
    그 외에는 'ambiguous' (사람이 직접 원문을 읽어야 함).
    """
    cands = [c for c in cands if c['pct'] < 99.5]  # 3년 후 100% 등 미래시점 배제
    valid = []
    for c in cands:
        recalc = None
        used_total = None
        if c.get('local_total'):
            recalc = c['qty'] / c['local_total'] * 100
            used_total = 'local'
        elif use_db_fallback and db_total:
            recalc = c['qty'] / db_total * 100
            used_total = 'db'
        if recalc is not None and abs(recalc - c['pct']) <= tol:
            c2 = dict(c)
            c2['used_total'] = used_total
            valid.append(c2)

    def resolve(group):
        if not group:
            return None
        g = sorted(group, key=lambda c: c['pos'])
        pcts = [c['pct'] for c in g]
        last_pct = g[-1]['pct']
        if all(abs(p - last_pct) <= 1.0 for p in pcts):
            return last_pct
        return None

    if valid:
        not_pre = [c for c in valid if c.get('correction_tag') != 'pre']
        pool = not_pre if not_pre else valid

        table_valid = [c for c in pool if c['source'] in ('first_row', 'subtotal_row')]
        result = resolve(table_valid)
        if result is not None:
            return 'confident', result, f'{len(table_valid)}/{len(cands)}_valid(table)'
        result = resolve(pool)
        if result is not None:
            return 'confident', result, f'{len(pool)}/{len(cands)}_valid'

    # 총수 검증으로 못 거른 경우 -> 동일 문구가 문서 내에서 반복되는지로 판단.
    # DART 신고서는 위험요소 요약/상세 섹션에서 같은 문장을 반복하는 경우가
    # 흔하다: 여러 번 반복되는 (주식수,비율) 쌍은 한 번만 나오는 값보다
    # 신뢰도가 높다.
    pool2 = [c for c in cands if c.get('correction_tag') != 'pre'] or cands
    clusters = {}
    for c in pool2:
        clusters.setdefault((c['qty'], round(c['pct'], 1)), []).append(c)
    ranked = sorted(clusters.values(), key=lambda g: (-len(g), -max(x['pos'] for x in g)))
    if ranked and len(ranked[0]) >= 2 and (len(ranked) == 1 or len(ranked[0]) > len(ranked[1])):
        winner = ranked[0]
        return 'confident', winner[0]['pct'], f'majority_{len(winner)}_of_{len(pool2)}'

    if not valid:
        return 'ambiguous', None, f'{len(cands)}_candidates_none_valid'
    return 'ambiguous', None, f'disagreement:{[c["pct"] for c in valid]}'


def find_doc_path(회사명):
    d = os.path.join(DOCS_DIR, 회사명)
    if not os.path.isdir(d):
        return None
    files = [f for f in os.listdir(d) if f.endswith('.xml')]
    if len(files) != 1:
        return None
    return os.path.join(d, files[0])


def extract_for_company(회사명, db_total):
    """회사명으로 캐시 문서를 찾아 (verdict, value, detail, doc_path)를 반환."""
    path = find_doc_path(회사명)
    if path is None:
        return 'ambiguous', None, 'no_cached_doc', None
    text = open(path, encoding='utf-8', errors='ignore').read()
    cands = all_candidates(text)
    verdict, value, detail = pick_value(cands, db_total)
    return verdict, value, detail, path


# ---------------------------------------------------------------------------
# Step 2: 캘리브레이션 (data_corrections의 45건 ground truth와 대조)
# ---------------------------------------------------------------------------

def run_calibration():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT corp_code, old_value, verified_value, verdict FROM data_corrections WHERE field='유통가능주식수비율'")
    truth = {r[0]: r for r in cur.fetchall()}

    cur.execute('''SELECT 회사명, dart_corp_code, 상장후주식수 FROM ipo_companies
                    WHERE "상장일">='2024-01-01' AND ("상장유형" IS NULL OR "상장유형"!='SPAC')
                      AND "확정공모가" IS NOT NULL''')
    rows = cur.fetchall()

    match, total = 0, 0
    wrong_confident = []
    lines = []
    for name, corp, db_total in rows:
        if corp not in truth:
            continue
        total += 1
        verdict, value, detail, _ = extract_for_company(name, db_total)
        _, old_v, verified_v, gt_verdict = truth[corp]
        if gt_verdict == 'unresolved':
            ok = (verdict == 'ambiguous')
        else:
            ok = (verdict == 'confident' and value is not None and abs(value - verified_v) <= 1.0)
        if verdict == 'confident' and not ok:
            wrong_confident.append((name, value, verified_v))
        if ok:
            match += 1
        flag = 'OK' if ok else 'MISS'
        lines.append(f'{flag} {name}: gt_verdict={gt_verdict} verified={verified_v} '
                      f'-> extractor={verdict} value={value} ({detail})')

    print(f'캘리브레이션 결과: {match}/{total} 일치 ({match/total*100:.1f}%)')
    print(f'confident인데 틀린 건(위험): {len(wrong_confident)}건')
    for w in wrong_confident:
        print('  WRONG-CONFIDENT', w)
    print()
    for line in lines:
        print(line)
    return match, total, wrong_confident


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibrate', action='store_true', help='data_corrections 45건 ground truth와 대조')
    args = parser.parse_args()
    if args.calibrate:
        run_calibration()
    else:
        parser.print_help()
