"""
pyecharts 图表生成 — 简洁风格，匹配 Film Archive 设计系统。

运行方式:
    python analysis/charts.py
"""

import os

from pyecharts.charts import Bar, Pie, Scatter, Line
from pyecharts import options as opts
from pyecharts.globals import ThemeType, CurrentConfig

from movie_analysis import (
    score_distribution,
    genre_distribution,
    country_distribution,
    top_directors,
    top_actors,
    top_movies,
    release_year_distribution,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Design Tokens ──────────────────────────────────────────────
# Matching the "Film Archive" Flask design system
INK       = "#1c1c1c"   # primary text
RED       = "#c1272d"   # accent
GRAY      = "#6b6b6b"   # secondary / muted
RULE      = "#e8e8e8"   # grid lines — very subtle
SURFACE   = "#f7f7f5"   # light surface
BAR_COLOR = "#3d3d4f"   # bar fill — dark blue-gray (quiet, not screaming blue)

# Clean init options — no heavy theme, minimal chrome
INIT_OPTS = opts.InitOpts(
    width="960px",
    height="540px",
    theme=ThemeType.LIGHT,
    bg_color="transparent",
)


def _base_style(chart: Bar) -> Bar:
    """Apply a consistent, minimal visual style to bar/line charts."""
    return chart.set_global_opts(
        title_opts=opts.TitleOpts(
            title_textstyle_opts=opts.TextStyleOpts(
                font_size=16,
                font_family="Noto Serif SC, serif",
                color=INK,
            ),
            pos_left="0",
            pos_top="0",
        ),
        legend_opts=opts.LegendOpts(is_show=False),
        tooltip_opts=opts.TooltipOpts(
            textstyle_opts=opts.TextStyleOpts(font_family="system-ui, sans-serif", font_size=13),
        ),
        xaxis_opts=opts.AxisOpts(
            axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color=RULE)),
            axislabel_opts=opts.LabelOpts(
                font_family="system-ui, sans-serif",
                font_size=11,
                color=GRAY,
            ),
        ),
        yaxis_opts=opts.AxisOpts(
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color=RULE, width=0.5, type_="solid"),
            ),
            axislabel_opts=opts.LabelOpts(
                font_family="system-ui, sans-serif",
                font_size=11,
                color=GRAY,
            ),
        ),
    )


def save(chart, filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    chart.render(path)
    print(f"  -> {path}")


# ── Individual Charts ──────────────────────────────────────────

def chart_score_distribution():
    """评分分布柱状图"""
    df = score_distribution()
    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(df["score_range"].tolist())
        .add_yaxis(
            "",
            df["cnt"].tolist(),
            itemstyle_opts=opts.ItemStyleOpts(color=BAR_COLOR, border_radius=[2, 2, 0, 0]),
            label_opts=opts.LabelOpts(
                is_show=True,
                position="top",
                font_family="system-ui, sans-serif",
                font_size=11,
                color=GRAY,
            ),
            bar_width="60%",
        )
    )
    _base_style(chart).set_global_opts(
        title_opts=opts.TitleOpts(
            title="评分分布",
            title_textstyle_opts=opts.TextStyleOpts(
                font_size=16,
                font_family="Noto Serif SC, serif",
                color=INK,
            ),
            pos_left="0",
        ),
        xaxis_opts=opts.AxisOpts(
            name="评分区间",
            name_location="center",
            name_gap=32,
            name_textstyle_opts=opts.TextStyleOpts(font_size=12, color=GRAY, font_family="system-ui, sans-serif"),
            axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color=RULE)),
            axislabel_opts=opts.LabelOpts(font_family="system-ui, sans-serif", font_size=11, color=GRAY),
        ),
        yaxis_opts=opts.AxisOpts(
            name="电影数量",
            name_textstyle_opts=opts.TextStyleOpts(font_size=12, color=GRAY, font_family="system-ui, sans-serif"),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color=RULE, width=0.5, type_="solid"),
            ),
            axislabel_opts=opts.LabelOpts(font_family="system-ui, sans-serif", font_size=11, color=GRAY),
        ),
    )
    save(chart, "score_distribution.html")


def chart_genre_distribution():
    """类型分布 — 水平柱状图 (可读性更好)"""
    df = genre_distribution().head(15)
    # Reverse for horizontal bar (bottom = highest count)
    names = df["genre_name"].tolist()[::-1]
    counts = df["cnt"].tolist()[::-1]

    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(names)
        .add_yaxis(
            "",
            counts,
            itemstyle_opts=opts.ItemStyleOpts(color=BAR_COLOR, border_radius=[0, 2, 2, 0]),
            label_opts=opts.LabelOpts(
                is_show=True,
                position="right",
                font_family="system-ui, sans-serif",
                font_size=11,
                color=GRAY,
            ),
            bar_width="55%",
        )
        .reversal_axis()
    )
    _base_style(chart).set_global_opts(
        title_opts=opts.TitleOpts(
            title="类型分布",
            title_textstyle_opts=opts.TextStyleOpts(
                font_size=16,
                font_family="Noto Serif SC, serif",
                color=INK,
            ),
            pos_left="0",
        ),
        xaxis_opts=opts.AxisOpts(
            name="电影数量",
            name_textstyle_opts=opts.TextStyleOpts(font_size=12, color=GRAY, font_family="system-ui, sans-serif"),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color=RULE, width=0.5),
            ),
            axislabel_opts=opts.LabelOpts(font_size=11, color=GRAY),
        ),
        yaxis_opts=opts.AxisOpts(
            axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color=RULE)),
            axislabel_opts=opts.LabelOpts(
                font_family="Noto Serif SC, serif",
                font_size=12,
                color=INK,
            ),
        ),
    )
    save(chart, "genre_distribution.html")


def chart_country_distribution():
    """国家/地区分布 — 水平柱状图"""
    df = country_distribution()
    names = df["primary_country"].tolist()[::-1]
    counts = df["cnt"].tolist()[::-1]

    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(names)
        .add_yaxis(
            "",
            counts,
            itemstyle_opts=opts.ItemStyleOpts(color=BAR_COLOR, border_radius=[0, 2, 2, 0]),
            label_opts=opts.LabelOpts(
                is_show=True,
                position="right",
                font_family="system-ui, sans-serif",
                font_size=11,
                color=GRAY,
            ),
            bar_width="55%",
        )
        .reversal_axis()
    )
    _base_style(chart).set_global_opts(
        title_opts=opts.TitleOpts(
            title="制片国家 / 地区",
            title_textstyle_opts=opts.TextStyleOpts(
                font_size=16,
                font_family="Noto Serif SC, serif",
                color=INK,
            ),
            pos_left="0",
        ),
        xaxis_opts=opts.AxisOpts(
            name="电影数量",
            name_textstyle_opts=opts.TextStyleOpts(font_size=12, color=GRAY, font_family="system-ui, sans-serif"),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color=RULE, width=0.5),
            ),
            axislabel_opts=opts.LabelOpts(font_size=11, color=GRAY),
        ),
        yaxis_opts=opts.AxisOpts(
            axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color=RULE)),
            axislabel_opts=opts.LabelOpts(
                font_family="Noto Serif SC, serif",
                font_size=12,
                color=INK,
            ),
        ),
    )
    save(chart, "country_distribution.html")


def chart_top_directors():
    """导演排行榜 — 水平柱状图，高评分用红色标注"""
    df = top_directors(3)
    names = df["person_name"].tolist()[::-1]
    scores = df["avg_score"].tolist()[::-1]

    # Top 3 bars get accent color
    n = len(scores)
    colors = [RED if i >= n - 3 else BAR_COLOR for i in range(n)]

    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(names)
        .add_yaxis(
            "",
            scores,
            itemstyle_opts=opts.ItemStyleOpts(
                color=None,  # Use per-item colors
                border_radius=[0, 2, 2, 0],
            ),
            label_opts=opts.LabelOpts(
                is_show=True,
                position="right",
                font_family="system-ui, sans-serif",
                font_size=11,
                color=GRAY,
                formatter="{c} 分",
            ),
            bar_width="55%",
        )
        .reversal_axis()
        .set_colors(colors)
    )
    _base_style(chart).set_global_opts(
        title_opts=opts.TitleOpts(
            title="导演平均评分",
            title_textstyle_opts=opts.TextStyleOpts(
                font_size=16,
                font_family="Noto Serif SC, serif",
                color=INK,
            ),
            subtitle="至少 3 部作品",
            subtitle_textstyle_opts=opts.TextStyleOpts(
                font_size=12, color=GRAY, font_family="system-ui, sans-serif"
            ),
            pos_left="0",
        ),
        xaxis_opts=opts.AxisOpts(
            name="平均评分",
            min_=6,
            name_textstyle_opts=opts.TextStyleOpts(font_size=12, color=GRAY, font_family="system-ui, sans-serif"),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color=RULE, width=0.5),
            ),
            axislabel_opts=opts.LabelOpts(font_size=11, color=GRAY),
        ),
        yaxis_opts=opts.AxisOpts(
            axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color=RULE)),
            axislabel_opts=opts.LabelOpts(
                font_family="Noto Serif SC, serif",
                font_size=12,
                color=INK,
            ),
        ),
    )
    save(chart, "top_directors.html")


def chart_top_movies():
    """高分电影 — 水平柱状图"""
    df = top_movies(20)
    names = df["movie_name"].tolist()[::-1]
    scores = df["douban_score"].tolist()[::-1]

    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(names)
        .add_yaxis(
            "",
            scores,
            itemstyle_opts=opts.ItemStyleOpts(color=BAR_COLOR, border_radius=[0, 2, 2, 0]),
            label_opts=opts.LabelOpts(
                is_show=True,
                position="right",
                font_family="system-ui, sans-serif",
                font_size=10,
                color=GRAY,
                formatter="{c}",
            ),
            bar_width="55%",
        )
        .reversal_axis()
    )
    _base_style(chart).set_global_opts(
        title_opts=opts.TitleOpts(
            title="高分电影 Top 20",
            title_textstyle_opts=opts.TextStyleOpts(
                font_size=16,
                font_family="Noto Serif SC, serif",
                color=INK,
            ),
            subtitle="评价人数 > 1000",
            subtitle_textstyle_opts=opts.TextStyleOpts(
                font_size=12, color=GRAY, font_family="system-ui, sans-serif"
            ),
            pos_left="0",
        ),
        xaxis_opts=opts.AxisOpts(
            name="豆瓣评分",
            min_=7.5,
            name_textstyle_opts=opts.TextStyleOpts(font_size=12, color=GRAY, font_family="system-ui, sans-serif"),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color=RULE, width=0.5),
            ),
            axislabel_opts=opts.LabelOpts(font_size=11, color=GRAY),
        ),
        yaxis_opts=opts.AxisOpts(
            axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color=RULE)),
            axislabel_opts=opts.LabelOpts(
                font_family="system-ui, sans-serif",
                font_size=11,
                color=INK,
            ),
        ),
    )
    save(chart, "top_movies.html")


def chart_release_year():
    """上映年份趋势 — 面积图风格折线"""
    df = release_year_distribution()
    df = df[df["year"] != "未知"]

    chart = (
        Line(init_opts=INIT_OPTS)
        .add_xaxis(df["year"].tolist())
        .add_yaxis(
            "",
            df["cnt"].tolist(),
            is_smooth=True,
            is_symbol_show=False,
            linestyle_opts=opts.LineStyleOpts(color=BAR_COLOR, width=2),
            areastyle_opts=opts.AreaStyleOpts(opacity=0.08, color=BAR_COLOR),
        )
    )
    _base_style(chart).set_global_opts(
        title_opts=opts.TitleOpts(
            title="上映年份趋势",
            title_textstyle_opts=opts.TextStyleOpts(
                font_size=16,
                font_family="Noto Serif SC, serif",
                color=INK,
            ),
            pos_left="0",
        ),
        legend_opts=opts.LegendOpts(is_show=False),
        xaxis_opts=opts.AxisOpts(
            name="年份",
            name_location="center",
            name_gap=32,
            name_textstyle_opts=opts.TextStyleOpts(font_size=12, color=GRAY, font_family="system-ui, sans-serif"),
            axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color=RULE)),
            axislabel_opts=opts.LabelOpts(font_family="system-ui, sans-serif", font_size=10, color=GRAY, rotate=45),
        ),
        yaxis_opts=opts.AxisOpts(
            name="电影数量",
            name_textstyle_opts=opts.TextStyleOpts(font_size=12, color=GRAY, font_family="system-ui, sans-serif"),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(color=RULE, width=0.5, type_="solid"),
            ),
            axislabel_opts=opts.LabelOpts(font_family="system-ui, sans-serif", font_size=11, color=GRAY),
        ),
    )
    save(chart, "release_year.html")


# ── Generate All ───────────────────────────────────────────────

def generate_all():
    """Generate all charts."""
    print("Generating charts (Film Archive style)...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    charts = [
        ("评分分布",   chart_score_distribution),
        ("类型分布",   chart_genre_distribution),
        ("国家分布",   chart_country_distribution),
        ("导演排行",   chart_top_directors),
        ("高分电影",   chart_top_movies),
        ("上映趋势",   chart_release_year),
    ]

    for name, func in charts:
        try:
            print(f"  [{name}]...")
            func()
        except Exception as e:
            print(f"  [{name}] FAILED: {e}")

    print(f"\nAll charts saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    generate_all()
