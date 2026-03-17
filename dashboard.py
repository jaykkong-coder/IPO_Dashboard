"""
IPO Dashboard - Streamlit
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import os
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipo_data.db")

st.set_page_config(
    page_title="IPO Dashboard",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ===== 스타일 =====
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; max-width: 1400px; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #667eea11, #764ba211);
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 12px 16px;
    }
    [data-testid="stMetricValue"] { font-size: 1.3rem; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem; color: #666; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 20px;
        font-weight: 600;
    }
    div[data-testid="stExpander"] { border: 1px solid #e8e8e8; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)


# ===== 포맷 헬퍼 =====
def fmt_num(v, suffix=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:,.0f}{suffix}"

def fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:.1f}%"

def fmt_mult(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:.1f}x"

def fmt_shares_m(v):
    """주식수를 백만주 단위로"""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v / 1000000:.1f}M"

def fmt_won(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:,.0f}원"

def fmt_억(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:,.0f}억"


@st.cache_data(ttl=60)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM ipo_companies WHERE 처리상태 = 'completed' ORDER BY 상장일 DESC",
        conn,
    )
    conn.close()
    # 파생 컬럼
    df["상장월"] = pd.to_datetime(df["상장일"]).dt.to_period("M").astype(str)
    df["상장연도"] = pd.to_datetime(df["상장일"]).dt.year
    df["공모주식수_M"] = df["공모주식수"] / 1e6
    df["신주_M"] = df["신주"] / 1e6
    df["구주_M"] = df["구주"] / 1e6
    df["상장후주식수_M"] = df["상장후주식수"] / 1e6
    df["유통가능주식수_M"] = df["유통가능주식수"] / 1e6
    return df


def format_display_df(df):
    """테이블 표시용 포맷팅"""
    display = df.copy()
    rename = {
        "적용이익_백만원": "적용이익(백만)",
        "적정시가총액_억원": "적정시총(억)",
        "기준시가총액_억원": "기준시총(억)",
        "확정공모금액_억원": "공모금액(억)",
        "인수수수료총액_억원": "수수료(억)",
        "인수수수료율": "수수료율(%)",
        "할인율_하단": "할인(하)",
        "할인율_상단": "할인(상)",
        "공모가밴드_하단": "밴드(하)",
        "공모가밴드_상단": "밴드(상)",
        "공모가밴드_중간값": "밴드(중)",
        "상단대비확정가비율": "상단비(%)",
        "유통가능주식수비율": "유통비율(%)",
        "공모주식수_M": "공모(M주)",
        "신주_M": "신주(M주)",
        "구주_M": "구주(M주)",
        "상장후주식수_M": "상장후(M주)",
    }
    display = display.rename(columns=rename)
    return display


def main():
    if not os.path.exists(DB_PATH):
        st.error("DB 파일이 없습니다. pipeline.py를 먼저 실행하세요.")
        return

    df = load_data()
    if df.empty:
        st.warning("데이터가 없습니다.")
        return

    # ===== 헤더 =====
    st.markdown("## IPO Dashboard")
    st.markdown(f"<span style='color:#888; font-size:0.85rem;'>2025년~ 신규 상장법인 밸류에이션 분석 | {len(df)}개 기업</span>", unsafe_allow_html=True)

    # ===== 상단 필터 (사이드바 대신) =====
    with st.expander("필터", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            markets = ["전체"] + sorted(df["시장구분"].dropna().unique().tolist())
            sel_market = st.selectbox("시장구분", markets, label_visibility="collapsed")
        with fc2:
            listing_types = ["전체"] + sorted(df["상장유형"].dropna().unique().tolist())
            sel_type = st.selectbox("상장유형", listing_types, label_visibility="collapsed")
        with fc3:
            methods = ["전체"] + sorted(df["평가방법"].dropna().unique().tolist())
            sel_method = st.selectbox("평가방법", methods, label_visibility="collapsed")
        with fc4:
            if df["상장일"].notna().any():
                dates = pd.to_datetime(df["상장일"].dropna())
                date_range = st.date_input(
                    "상장일",
                    value=(dates.min().date(), dates.max().date()),
                    label_visibility="collapsed",
                )

    # 필터 적용
    filtered = df.copy()
    if sel_market != "전체":
        filtered = filtered[filtered["시장구분"] == sel_market]
    if sel_type != "전체":
        filtered = filtered[filtered["상장유형"] == sel_type]
    if sel_method != "전체":
        filtered = filtered[filtered["평가방법"] == sel_method]
    if "date_range" in dir() and len(date_range) == 2:
        filtered = filtered[
            (pd.to_datetime(filtered["상장일"]) >= pd.Timestamp(date_range[0]))
            & (pd.to_datetime(filtered["상장일"]) <= pd.Timestamp(date_range[1]))
        ]

    # ===== KPI =====
    valid = filtered[filtered["기준시가총액_억원"].notna()]
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("기업수", f"{len(filtered)}")
    k2.metric("평균 시가총액", fmt_억(valid["기준시가총액_억원"].mean()) if not valid.empty else "-")
    k3.metric("평균 멀티플", fmt_mult(filtered["적용멀티플"].mean()) if filtered["적용멀티플"].notna().any() else "-")
    k4.metric("평균 할인율", fmt_pct(filtered["할인율_하단"].mean()) if filtered["할인율_하단"].notna().any() else "-")
    k5.metric("공모가 상단+", f"{len(filtered[filtered['공모가최종'].isin(['상단', '상단초과'])])}/{len(filtered)}")
    k6.metric("평균 수수료율", fmt_pct(filtered["인수수수료율"].mean()) if filtered["인수수수료율"].notna().any() else "-")

    st.markdown("")

    # ===== 탭 =====
    tab1, tab2, tab3, tab4 = st.tabs(["기업 목록", "차트 분석", "기업 상세", "통계 / 시계열"])

    # ────────────────── 탭1: 기업 목록 ──────────────────
    with tab1:
        display_cols = [
            "회사명", "상장일", "시장구분", "상장유형", "업종",
            "대표주관회사", "평가방법", "적용멀티플",
            "적용이익_백만원", "적정시가총액_억원",
            "할인율_하단", "할인율_상단",
            "공모가밴드_하단", "공모가밴드_상단",
            "확정공모가", "공모가최종", "상단대비확정가비율",
            "기준시가총액_억원", "확정공모금액_억원",
            "주당평가가액", "공모비율",
            "공모주식수_M", "신주_M", "구주_M",
            "상장후주식수_M", "유통가능주식수비율",
            "인수수수료총액_억원", "인수수수료율",
        ]
        available = [c for c in display_cols if c in filtered.columns]
        disp = format_display_df(filtered[available])

        # 숫자 포맷
        col_config = {}
        for col in disp.columns:
            if "억" in col or "백만" in col:
                col_config[col] = st.column_config.NumberColumn(format="%,.0f")
            elif "%" in col or "할인" in col:
                col_config[col] = st.column_config.NumberColumn(format="%.1f")
            elif "M주" in col:
                col_config[col] = st.column_config.NumberColumn(format="%.1f")
            elif col == "적용멀티플":
                col_config[col] = st.column_config.NumberColumn(format="%.1f")
            elif col in ("확정공모가", "주당평가가액", "밴드(하)", "밴드(상)", "밴드(중)"):
                col_config[col] = st.column_config.NumberColumn(format="%,.0f")

        st.dataframe(
            disp,
            use_container_width=True,
            hide_index=True,
            height=650,
            column_config=col_config,
        )

    # ────────────────── 탭2: 차트 분석 ──────────────────
    with tab2:
        if len(filtered) < 2:
            st.info("2개 이상의 기업이 필요합니다.")
        else:
            # Row 1: 4개 분포 차트
            c1, c2 = st.columns(2)

            with c1:
                # 공모가 위치 분포
                if filtered["공모가최종"].notna().any():
                    dist = filtered["공모가최종"].value_counts()
                    colors = {"상단": "#2196F3", "상단초과": "#1565C0", "밴드내": "#4CAF50",
                              "하단": "#FF9800", "하단미만": "#F44336"}
                    fig = px.pie(values=dist.values, names=dist.index, title="공모가 확정 위치",
                                 color=dist.index, color_discrete_map=colors, hole=0.4)
                    fig.update_layout(margin=dict(t=40, b=20, l=20, r=20), height=320,
                                      legend=dict(orientation="h", y=-0.1))
                    st.plotly_chart(fig, use_container_width=True)

            with c2:
                # 평가방법 + 상장유형 Sunburst
                if filtered["평가방법"].notna().any() and filtered["상장유형"].notna().any():
                    sun_df = filtered[filtered["평가방법"].notna() & filtered["상장유형"].notna()]
                    fig = px.sunburst(sun_df, path=["상장유형", "평가방법"], title="상장유형 > 평가방법",
                                      color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig.update_layout(margin=dict(t=40, b=20, l=20, r=20), height=320)
                    st.plotly_chart(fig, use_container_width=True)

            c3, c4 = st.columns(2)

            with c3:
                # 할인율 범위 차트 (기업별)
                disc_df = filtered[filtered["할인율_하단"].notna() & filtered["할인율_상단"].notna()].copy()
                if not disc_df.empty:
                    disc_df = disc_df.sort_values("할인율_하단", ascending=False).head(25)
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        y=disc_df["회사명"], x=disc_df["할인율_상단"],
                        orientation="h", name="할인율 상단", marker_color="#90CAF9",
                    ))
                    fig.add_trace(go.Bar(
                        y=disc_df["회사명"],
                        x=disc_df["할인율_하단"] - disc_df["할인율_상단"],
                        orientation="h", name="추가 할인 폭", marker_color="#1565C0",
                        base=disc_df["할인율_상단"],
                    ))
                    fig.update_layout(title="기업별 할인율 범위 (%)", barmode="stack",
                                      height=500, margin=dict(l=120, t=40, b=30),
                                      legend=dict(orientation="h", y=1.05),
                                      xaxis_title="%")
                    st.plotly_chart(fig, use_container_width=True)

            with c4:
                # 멀티플 vs 시가총액 Scatter
                scatter_df = filtered[
                    filtered["적용멀티플"].notna()
                    & filtered["기준시가총액_억원"].notna()
                    & filtered["확정공모금액_억원"].notna()
                    & (filtered["확정공모금액_억원"] > 0)
                ].copy()
                if not scatter_df.empty:
                    fig = px.scatter(
                        scatter_df, x="적용멀티플", y="기준시가총액_억원",
                        text="회사명", color="평가방법",
                        size="확정공모금액_억원",
                        title="멀티플 vs 시가총액",
                        labels={"적용멀티플": "멀티플 (배)", "기준시가총액_억원": "시가총액 (억원)"},
                        color_discrete_sequence=px.colors.qualitative.Set2,
                    )
                    fig.update_traces(textposition="top center", textfont_size=8)
                    fig.update_layout(height=500, margin=dict(t=40, b=30))
                    st.plotly_chart(fig, use_container_width=True)

            # Row 3: 월별 추이
            st.markdown("---")
            if filtered["상장일"].notna().any():
                monthly = filtered.copy()
                monthly_grp = monthly.groupby("상장월").agg(
                    건수=("회사명", "count"),
                    평균시총=("기준시가총액_억원", "mean"),
                    평균멀티플=("적용멀티플", "mean"),
                    총공모금액=("확정공모금액_억원", "sum"),
                ).reset_index()

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                                    subplot_titles=("월별 IPO 건수 & 총 공모금액", "월별 평균 멀티플"))

                fig.add_trace(go.Bar(x=monthly_grp["상장월"], y=monthly_grp["건수"],
                                     name="건수", marker_color="#42A5F5", opacity=0.8), row=1, col=1)
                fig.add_trace(go.Scatter(x=monthly_grp["상장월"], y=monthly_grp["총공모금액"],
                                         name="총공모금액(억)", yaxis="y2", mode="lines+markers",
                                         line=dict(color="#FF7043", width=2)), row=1, col=1)

                fig.add_trace(go.Scatter(x=monthly_grp["상장월"], y=monthly_grp["평균멀티플"],
                                         name="평균 멀티플", mode="lines+markers+text",
                                         text=[f"{v:.1f}" if not np.isnan(v) else "" for v in monthly_grp["평균멀티플"]],
                                         textposition="top center",
                                         line=dict(color="#AB47BC", width=2)), row=2, col=1)

                fig.update_layout(height=500, margin=dict(t=60, b=30),
                                  legend=dict(orientation="h", y=1.12))
                fig.update_yaxes(title_text="건수", row=1, col=1)
                fig.update_yaxes(title_text="멀티플(배)", row=2, col=1)
                st.plotly_chart(fig, use_container_width=True)

    # ────────────────── 탭3: 기업 상세 ──────────────────
    with tab3:
        if filtered.empty:
            st.info("기업을 선택하세요.")
        else:
            selected = st.selectbox("기업 선택", filtered["회사명"].tolist())
            c = filtered[filtered["회사명"] == selected].iloc[0]

            # 카드 레이아웃
            col_l, col_r = st.columns(2)

            with col_l:
                st.markdown("#### 기본 정보")
                rows_info = [
                    ("업종", c.get("업종")),
                    ("주요제품", c.get("주요제품")),
                    ("상장일", c.get("상장일")),
                    ("시장 / 유형", f"{c.get('시장구분', '-')} | {c.get('상장유형', '-')}"),
                    ("대표주관", c.get("대표주관회사")),
                ]
                for label, val in rows_info:
                    st.markdown(f"**{label}** : {val if val else '-'}")

                st.markdown("#### 밸류에이션")
                val_rows = [
                    ("평가방법", c.get("평가방법")),
                    ("적용멀티플", fmt_mult(c.get("적용멀티플"))),
                    ("적용이익", fmt_num(c.get("적용이익_백만원"), "백만원")),
                    ("적정시가총액", fmt_억(c.get("적정시가총액_억원"))),
                    ("할인율", f"{fmt_pct(c.get('할인율_하단'))} ~ {fmt_pct(c.get('할인율_상단'))}"
                     if c.get("할인율_하단") else "-"),
                    ("주당 평가가액", fmt_won(c.get("주당평가가액"))),
                ]
                for label, val in val_rows:
                    st.markdown(f"**{label}** : {val}")

            with col_r:
                st.markdown("#### 공모가격")
                price_rows = [
                    ("공모가 밴드", f"{fmt_won(c.get('공모가밴드_하단'))} ~ {fmt_won(c.get('공모가밴드_상단'))}"
                     if c.get("공모가밴드_하단") else "-"),
                    ("확정공모가", fmt_won(c.get("확정공모가"))),
                    ("밴드 위치", c.get("공모가최종")),
                    ("상단대비", fmt_pct(c.get("상단대비확정가비율"))),
                ]
                for label, val in price_rows:
                    st.markdown(f"**{label}** : {val if val else '-'}")

                st.markdown("#### 공모 규모")
                size_rows = [
                    ("기준시가총액", fmt_억(c.get("기준시가총액_억원"))),
                    ("공모금액", fmt_억(c.get("확정공모금액_억원"))),
                    ("공모비율", fmt_pct(c.get("공모비율"))),
                    ("공모주식수", fmt_shares_m(c.get("공모주식수"))),
                    ("신주 / 구주", f"{fmt_shares_m(c.get('신주'))} / {fmt_shares_m(c.get('구주'))}"),
                    ("상장후 주식수", fmt_shares_m(c.get("상장후주식수"))),
                    ("유통가능비율", fmt_pct(c.get("유통가능주식수비율"))),
                    ("인수수수료", f"{fmt_억(c.get('인수수수료총액_억원'))} ({fmt_pct(c.get('인수수수료율'))})"
                     if c.get("인수수수료총액_억원") else "-"),
                ]
                for label, val in size_rows:
                    st.markdown(f"**{label}** : {val}")

    # ────────────────── 탭4: 통계 / 시계열 ──────────────────
    with tab4:
        if len(filtered) < 2:
            st.info("2개 이상의 기업이 필요합니다.")
        else:
            # 주관사별 실적
            st.markdown("#### 주관사별 실적")
            if filtered["대표주관회사"].notna().any():
                uw_list = []
                for _, row in filtered.iterrows():
                    uw = row.get("대표주관회사", "")
                    if uw:
                        for u in str(uw).split(","):
                            u = u.strip()
                            if u:
                                uw_list.append({
                                    "주관사": u,
                                    "시가총액": row.get("기준시가총액_억원", 0) or 0,
                                    "공모금액": row.get("확정공모금액_억원", 0) or 0,
                                    "수수료율": row.get("인수수수료율"),
                                })
                if uw_list:
                    uw_df = pd.DataFrame(uw_list)
                    uw_stats = uw_df.groupby("주관사").agg(
                        건수=("주관사", "count"),
                        총공모금액=("공모금액", "sum"),
                        평균시총=("시가총액", "mean"),
                        평균수수료율=("수수료율", "mean"),
                    ).sort_values("건수", ascending=False).reset_index()

                    c1, c2 = st.columns([2, 1])
                    with c1:
                        fig = px.bar(uw_stats.head(15), x="주관사", y="건수",
                                     color="총공모금액", title="주관사별 IPO 건수 (공모금액 색상)",
                                     color_continuous_scale="Blues",
                                     labels={"총공모금액": "총공모(억)"})
                        fig.update_layout(height=350, margin=dict(t=40, b=30))
                        st.plotly_chart(fig, use_container_width=True)
                    with c2:
                        st.dataframe(
                            uw_stats.style.format({
                                "총공모금액": "{:,.0f}",
                                "평균시총": "{:,.0f}",
                                "평균수수료율": "{:.1f}",
                            }),
                            use_container_width=True, height=350, hide_index=True,
                        )

            st.markdown("---")

            # 상장유형별 비교
            st.markdown("#### 상장유형별 비교")
            if filtered["상장유형"].notna().any():
                type_stats = filtered.groupby("상장유형").agg(
                    기업수=("회사명", "count"),
                    평균멀티플=("적용멀티플", "mean"),
                    평균할인율=("할인율_하단", "mean"),
                    평균시총=("기준시가총액_억원", "mean"),
                    평균공모비율=("공모비율", "mean"),
                    평균유통비율=("유통가능주식수비율", "mean"),
                ).reset_index()

                c1, c2 = st.columns(2)
                with c1:
                    fig = px.bar(type_stats, x="상장유형", y=["평균멀티플", "평균할인율"],
                                 barmode="group", title="상장유형별 멀티플 & 할인율",
                                 color_discrete_sequence=["#42A5F5", "#FF7043"])
                    fig.update_layout(height=320, margin=dict(t=40, b=30))
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    fig = px.bar(type_stats, x="상장유형", y=["평균공모비율", "평균유통비율"],
                                 barmode="group", title="상장유형별 공모비율 & 유통비율",
                                 color_discrete_sequence=["#66BB6A", "#AB47BC"])
                    fig.update_layout(height=320, margin=dict(t=40, b=30))
                    st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # 업종별 분포
            st.markdown("#### 업종별 분포")
            c1, c2 = st.columns(2)
            with c1:
                if filtered["업종"].notna().any():
                    sector = filtered["업종"].value_counts().head(12)
                    fig = px.bar(x=sector.values, y=sector.index, orientation="h",
                                 title="업종별 IPO 건수 (Top 12)",
                                 labels={"x": "건수", "y": ""},
                                 color=sector.values, color_continuous_scale="Viridis")
                    fig.update_layout(height=400, margin=dict(l=200, t=40, b=30),
                                      yaxis=dict(autorange="reversed"), showlegend=False)
                    fig.update_coloraxes(showscale=False)
                    st.plotly_chart(fig, use_container_width=True)

            with c2:
                # 평가방법별 멀티플 분포
                if filtered["평가방법"].notna().any() and filtered["적용멀티플"].notna().any():
                    box_df = filtered[filtered["적용멀티플"].notna() & filtered["평가방법"].notna()]
                    fig = px.box(box_df, x="평가방법", y="적용멀티플", points="all",
                                 title="평가방법별 멀티플 분포",
                                 labels={"적용멀티플": "멀티플(배)"},
                                 color="평가방법", color_discrete_sequence=px.colors.qualitative.Set2)
                    fig.update_layout(height=400, margin=dict(t=40, b=30), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # 시계열: 월별 평균 할인율 & 멀티플 추이
            st.markdown("#### 시계열 추이")
            if filtered["상장일"].notna().any():
                ts = filtered.groupby("상장월").agg(
                    평균멀티플=("적용멀티플", "mean"),
                    평균할인율=("할인율_하단", "mean"),
                    평균시총=("기준시가총액_억원", "mean"),
                    평균수수료율=("인수수수료율", "mean"),
                    건수=("회사명", "count"),
                ).reset_index()

                fig = make_subplots(rows=2, cols=2, shared_xaxes=True,
                                    subplot_titles=("평균 멀티플", "평균 할인율(%)",
                                                    "평균 시가총액(억)", "평균 수수료율(%)"),
                                    vertical_spacing=0.12, horizontal_spacing=0.08)

                fig.add_trace(go.Scatter(x=ts["상장월"], y=ts["평균멀티플"], mode="lines+markers",
                                         line=dict(color="#42A5F5"), name="멀티플"), row=1, col=1)
                fig.add_trace(go.Scatter(x=ts["상장월"], y=ts["평균할인율"], mode="lines+markers",
                                         line=dict(color="#FF7043"), name="할인율"), row=1, col=2)
                fig.add_trace(go.Bar(x=ts["상장월"], y=ts["평균시총"],
                                     marker_color="#66BB6A", name="시총"), row=2, col=1)
                fig.add_trace(go.Scatter(x=ts["상장월"], y=ts["평균수수료율"], mode="lines+markers",
                                         line=dict(color="#AB47BC"), name="수수료율"), row=2, col=2)

                fig.update_layout(height=500, margin=dict(t=60, b=30), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
