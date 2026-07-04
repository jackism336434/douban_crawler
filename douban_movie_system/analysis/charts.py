"""
pyecharts 图表生成。

运行方式:
    python analysis/charts.py
"""

import os
import sys

from pyecharts.charts import Bar, Pie, Scatter, Line
from pyecharts import options as opts
from pyecharts.globals import ThemeType

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

# 通用的初始化选项
INIT_OPTS = opts.InitOpts(
    width="1000px",
    height="600px",
    theme=ThemeType.ROMANTIC,
)


def save(chart, filename: str):
    """保存图表为 HTML"""
    path = os.path.join(OUTPUT_DIR, filename)
    chart.render(path)
    print(f"  -> {path}")


def chart_score_distribution():
    """评分分布柱状图"""
    df = score_distribution()
    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(df["score_range"].tolist())
        .add_yaxis("电影数量", df["cnt"].tolist())
        .set_global_opts(
            title_opts=opts.TitleOpts(title="豆瓣电影评分分布"),
            xaxis_opts=opts.AxisOpts(name="评分区间"),
            yaxis_opts=opts.AxisOpts(name="电影数量"),
        )
    )
    save(chart, "score_distribution.html")


def chart_genre_distribution():
    """类型分布饼图"""
    df = genre_distribution().head(15)  # 取前15类型
    chart = (
        Pie(init_opts=INIT_OPTS)
        .add("", [list(z) for z in zip(df["genre_name"], df["cnt"])])
        .set_global_opts(title_opts=opts.TitleOpts(title="电影类型分布"))
        .set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {c}"))
    )
    save(chart, "genre_distribution.html")


def chart_country_distribution():
    """国家/地区分布柱状图"""
    df = country_distribution()
    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(df["primary_country"].tolist())
        .add_yaxis("电影数量", df["cnt"].tolist())
        .set_global_opts(
            title_opts=opts.TitleOpts(title="电影国家/地区分布 Top 20"),
            xaxis_opts=opts.AxisOpts(name="国家/地区", axislabel_opts=opts.LabelOpts(rotate=45)),
            yaxis_opts=opts.AxisOpts(name="电影数量"),
        )
    )
    save(chart, "country_distribution.html")


def chart_top_directors():
    """导演排行榜"""
    df = top_directors(3)
    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(df["person_name"].tolist())
        .add_yaxis("平均评分", df["avg_score"].tolist())
        .set_global_opts(
            title_opts=opts.TitleOpts(title="导演平均评分排行榜 (≥3部)"),
            xaxis_opts=opts.AxisOpts(name="导演", axislabel_opts=opts.LabelOpts(rotate=45)),
            yaxis_opts=opts.AxisOpts(name="平均评分", min_=6),
        )
    )
    save(chart, "top_directors.html")


def chart_top_movies():
    """高分电影排行榜"""
    df = top_movies(20)
    chart = (
        Bar(init_opts=INIT_OPTS)
        .add_xaxis(df["movie_name"].tolist()[::-1])  # 反转，高分在上
        .add_yaxis("豆瓣评分", df["douban_score"].tolist()[::-1])
        .reversal_axis()
        .set_global_opts(
            title_opts=opts.TitleOpts(title="高分电影 Top 20 (评价人数>1000)"),
            xaxis_opts=opts.AxisOpts(name="豆瓣评分", min_=8),
            yaxis_opts=opts.AxisOpts(name="电影", axislabel_opts=opts.LabelOpts(font_size=10)),
        )
    )
    save(chart, "top_movies.html")


def chart_release_year():
    """上映年份趋势"""
    df = release_year_distribution()
    # 过滤掉 "未知"
    df = df[df["year"] != "未知"]
    chart = (
        Line(init_opts=INIT_OPTS)
        .add_xaxis(df["year"].tolist())
        .add_yaxis("电影数量", df["cnt"].tolist(), is_smooth=True)
        .set_global_opts(
            title_opts=opts.TitleOpts(title="电影上映年份趋势"),
            xaxis_opts=opts.AxisOpts(name="年份", axislabel_opts=opts.LabelOpts(rotate=45)),
            yaxis_opts=opts.AxisOpts(name="电影数量"),
        )
    )
    save(chart, "release_year.html")


def generate_all():
    """生成所有图表"""
    print("Generating charts...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    charts = [
        ("评分分布", chart_score_distribution),
        ("类型分布", chart_genre_distribution),
        ("国家分布", chart_country_distribution),
        ("导演排行", chart_top_directors),
        ("高分电影", chart_top_movies),
        ("上映趋势", chart_release_year),
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
