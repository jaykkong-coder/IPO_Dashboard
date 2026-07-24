"""IPO 퍼포먼스 산점도 팩: 변수별 1페이지 = 1M/3M/6M/12M 초과수익률(x) vs 변수(y) 4분할.

색상: W=#2a78d6 / L=#eb6834 (dataviz 검증 팔레트), M=회색 배경(범례 명시).
표시범위는 양축 p1~p99 윈저라이즈(계산은 전체 데이터, 표시만 절단).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

import perf_common as pc

FONT = fm.FontProperties(fname="/mnt/c/Windows/Fonts/malgun.ttf")
plt.rcParams["font.family"] = FONT.get_name()
fm.fontManager.addfont("/mnt/c/Windows/Fonts/malgun.ttf")
plt.rcParams["axes.unicode_minus"] = False

C_W, C_L, C_M = "#2a78d6", "#eb6834", "#9aa0a6"
HORIZONS = ["1M", "3M", "6M", "12M"]

# (컬럼키, 표시명, 단위, y로그스케일)
VARIABLES = [
    ("float_ratio", "유통가능주식수비율", "%", False),
    ("lockup_ratio", "의무보유확약비율", "%", False),
    ("inst_ratio", "기관경쟁률", ":1", True),
    ("subs_ratio", "청약경쟁률(비례)", ":1", True),
    ("inst_count", "수요예측 참여기관수", "곳", False),
    ("offer_size", "확정공모금액", "억원", True),
    ("base_mcap", "기준시가총액", "억원", True),
    ("price_vs_band_top", "상단대비 확정가", "%", False),
    ("discount_top", "할인율(상단)", "%", False),
    ("offer_pct", "공모비율", "%", False),
    ("old_share_ratio", "구주매출 비중", "%", False),
    ("fee_rate", "인수수수료율", "%", False),
    ("multiple", "적용멀티플", "배", True),
    ("estimate_achievement", "추정치 달성률", "%", False),
]

EXTRA_SQL = """
SELECT dart_corp_code AS corp_code,
       "청약경쟁률_비례" AS subs_ratio, "수요예측_참여기관수" AS inst_count,
       "기준시가총액_억원" AS base_mcap, "할인율_상단" AS discount_top,
       "공모비율" AS offer_pct, "인수수수료율" AS fee_rate,
       "적용멀티플" AS multiple
FROM ipo_companies
"""


def load_frame() -> pd.DataFrame:
    con = pc.get_db()
    uni = pd.DataFrame(pc.load_universe(con))
    extra = pd.read_sql(EXTRA_SQL, con)
    tickers = pc.corp_to_stock_map()
    uni["stock_code"] = uni["corp_code"].map(tickers)
    px = pd.read_sql(
        """SELECT stock_code, horizon, excess_return FROM price_performance
           WHERE base_price_type='IPO'""", con)
    px = px.pivot(index="stock_code", columns="horizon", values="excess_return")
    flags = pd.read_sql(
        "SELECT stock_code, group_6m, estimate_achievement FROM analysis_flags", con)
    df = (uni.merge(extra, on="corp_code")
             .merge(px, left_on="stock_code", right_index=True, how="left")
             .merge(flags, on="stock_code", how="left"))
    new_s = df["new_shares"].fillna(0)
    old_s = df["old_shares"].fillna(0)
    tot = new_s + old_s
    df["old_share_ratio"] = np.where(tot > 0, old_s / tot * 100, np.nan)
    for col in ("multiple",):  # "25.5배" 등 문자열 방어
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _limits(s: pd.Series, log: bool):
    s = s.dropna()
    if s.empty:
        return None
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    if log:
        lo = max(lo, s[s > 0].min() if (s > 0).any() else 1)
    pad = (hi - lo) * 0.06 if hi > lo else 1
    return (lo - (0 if log else pad), hi + pad)


def draw_page(pdf, df, key, label, unit, logy):
    fig, axes = plt.subplots(2, 2, figsize=(11.7, 8.3))  # A4 가로
    fig.suptitle(f"{label} ({unit})  vs  공모가 대비 시장조정 초과수익률",
                 fontsize=14, fontproperties=FONT, fontweight="bold", y=0.98)
    ylim = _limits(df[key], logy)
    for ax, h in zip(axes.flat, HORIZONS):
        sub = df[[h, key, "group_6m"]].dropna(subset=[h, key])
        if logy:
            sub = sub[sub[key] > 0]
        for g, c, a, z in (("M", C_M, 0.35, 1), ("W", C_W, 0.75, 2), ("L", C_L, 0.75, 2)):
            gg = sub[sub["group_6m"] == g]
            ax.scatter(gg[h], gg[key], s=14, c=c, alpha=a, zorder=z,
                       edgecolors="white", linewidths=0.3)
        ung = sub[sub["group_6m"].isna()]  # 6M 미경과(그룹 없음)
        ax.scatter(ung[h], ung[key], s=14, c=C_M, alpha=0.2, zorder=0,
                   edgecolors="white", linewidths=0.3)
        rho = sub[h].rank().corr(sub[key].rank())  # spearman = 순위의 pearson (scipy 불요)
        ax.set_title(f"{h}   n={len(sub)}   ρ(spearman)={rho:+.2f}",
                     fontsize=10, fontproperties=FONT, loc="left")
        xlim = _limits(sub[h], False)
        if xlim:
            ax.set_xlim(xlim)
        if ylim:
            ax.set_ylim(ylim)
        if logy:
            ax.set_yscale("log")
        ax.axvline(0, color="#c9c9c9", lw=0.8, zorder=0)
        ax.grid(True, color="#ececec", lw=0.5, zorder=0)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.tick_params(labelsize=8)
        ax.set_xlabel(f"{h} 초과수익률 (%)", fontsize=9, fontproperties=FONT)
        ax.set_ylabel(f"{label} ({unit})", fontsize=9, fontproperties=FONT)
    handles = [
        plt.Line2D([], [], marker="o", ls="", color=C_W, label="Winner (6M 상위⅓)"),
        plt.Line2D([], [], marker="o", ls="", color=C_L, label="Loser (6M 하위⅓)"),
        plt.Line2D([], [], marker="o", ls="", color=C_M, alpha=0.5,
                   label="Middle·미분류 (배경)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9,
               prop=FONT, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    pdf.savefig(fig)
    plt.close(fig)


def main():
    df = load_frame()
    out = pc.ROOT / "compare_report" / "ipo_scatter_pack.pdf"
    with PdfPages(out) as pdf:
        # 안내 페이지
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.text(0.07, 0.88, "IPO 주가 퍼포먼스 산점도 팩", fontsize=22,
                 fontproperties=FONT, fontweight="bold")
        info = (
            f"대상: 2024.1~ 신규상장 {len(df)}사 (스팩·리츠·이전상장 제외)\n"
            "x축: 공모가 대비 시장조정 초과수익률(%) — ETF 프록시(KODEX200/코스닥150) 차감,\n"
            "        상장일+N캘린더월 이후 첫 거래일 종가 기준\n"
            "y축: 공모 구조·수요예측·실적 변수 14종 (페이지당 1변수 × 지평 4분할)\n"
            "색: 파랑=Winner, 오렌지=Loser (6M 초과수익률 3분위), 회색=Middle·6M 미경과\n"
            "ρ: 스피어만 순위상관 (전체 표본 기준, 표시범위만 p1~p99 절단)\n"
            "로그축: 기관경쟁률·청약경쟁률·공모금액·시총·멀티플"
        )
        fig.text(0.07, 0.52, info, fontsize=12, fontproperties=FONT, va="top",
                 linespacing=1.8)
        pdf.savefig(fig)
        plt.close(fig)
        for key, label, unit, logy in VARIABLES:
            draw_page(pdf, df, key, label, unit, logy)
    print(f"saved {out} ({1 + len(VARIABLES)} pages)")


if __name__ == "__main__":
    main()
