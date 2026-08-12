"""실문서에서 특정 표 구간만 잘라 테스트 fixture 파일로 저장.

Task 4b 교훈: 합성 <TD> fixture는 프로덕션(<TE>+ACODE)을 대표하지 못했다.
이 스크립트는 DART 원문에서 표 구간만 남기고 나머지(2MB 전체 문서)는 버려서,
재현 가능하면서도 fixture 크기를 작게 유지한다.

Usage:
    python3 tools/dump_fixture.py <rcept_no> <anchor_text> <out_path> [--chars N]

anchor_text 예:
    "3. 청약 및 배정현황"                  — 배정현황 표
    "의무보유확약기간별 배정현황"           — 확약표

anchor부터 다음 <SECTION-3 시작 전까지를 저장한다 (표+각주 정도만 남음).
"""
import argparse

import collect_impl_reports as cir


def extract_table_segment(text: str, anchor: str, max_chars: int = 20000) -> str:
    idx = text.find(anchor)
    if idx < 0:
        raise ValueError(f"anchor not found: {anchor!r}")
    seg = text[idx: idx + max_chars]
    # 첫 </TABLE-GROUP> 직후로 잘라 해당 표만 남긴다.
    # (다음 <SECTION-3 를 기준으로 자르면 표 뒤에 이어지는 각주/다음 절의
    #  무관한 표까지 딸려온다 — 실측 시 확약표 뒤에 바로 주요주주 지분변동
    #  섹션이 SECTION-3 마커 없이 이어지는 문서가 있었다.)
    end = seg.find("</TABLE-GROUP>")
    if end > 0:
        seg = seg[: end + len("</TABLE-GROUP>")]
    return seg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rcept_no")
    ap.add_argument("anchor")
    ap.add_argument("out_path")
    ap.add_argument("--chars", type=int, default=20000)
    args = ap.parse_args()

    text = cir.fetch_document(args.rcept_no)
    seg = extract_table_segment(text, args.anchor, args.chars)
    with open(args.out_path, "w", encoding="utf-8") as f:
        f.write(seg)
    print(f"saved {len(seg)} chars -> {args.out_path}")


if __name__ == "__main__":
    main()
