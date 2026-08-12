"""투설 캐시(docs/<회사명>/<rcept_no>.xml) 중 CP949로 인코딩됐지만 UTF-8이라고
잘못 선언된 파일을 UTF-8로 재인코딩한다 (Step 9 조사 결과).

verify_float_extractor.extract_for_company는 캐시 문서를 항상
open(path, encoding='utf-8', errors='ignore')로 읽는다. 2020~2021년
문서 상당수가 실제로는 CP949(EUC-KR)인데 XML 헤더는 encoding="utf-8"이라고
선언되어 있어, errors='ignore'가 깨진 바이트를 조용히 삭제하면서 "유통가능"
등 한글 키워드가 전부 소실된다 (confident 3/82, 1/98로 붕괴한 근본 원인).

verify_float_extractor.py의 추출 로직은 건드리지 않는다 -- 이 스크립트는
캐시 파일 내용만 UTF-8로 정정한다(같은 파일명, 폴더당 파일 1개 유지).
"""
import os

import perf_common as pc

DOCS = pc.ROOT / "docs"


def main():
    fixed, checked, still_bad = [], 0, []
    for d in sorted(DOCS.iterdir()):
        if not d.is_dir():
            continue
        xmls = [f for f in os.listdir(d) if f.endswith(".xml")]
        if len(xmls) != 1:
            continue
        checked += 1
        p = d / xmls[0]
        raw = p.read_bytes()
        try:
            raw.decode("utf-8", errors="strict")
            continue  # 이미 정상 UTF-8
        except UnicodeDecodeError:
            pass
        try:
            text = raw.decode("cp949", errors="strict")
        except UnicodeDecodeError as e:
            still_bad.append((d.name, str(e)))
            continue
        p.write_text(text, encoding="utf-8")
        fixed.append(d.name)
        print(f"[{len(fixed)}] {d.name} 재인코딩 (cp949->utf-8)")

    print(f"검사 {checked}건, 재인코딩 {len(fixed)}건, cp949로도 실패 {len(still_bad)}건")
    for name, err in still_bad:
        print(f"  실패: {name}: {err}")


if __name__ == "__main__":
    main()
