"""
豆瓣电影数据展示系统 (Flask)

运行方式:
    cd douban_movie_system
    python web/app.py
    # 浏览器打开 http://localhost:5000
"""

import os
import sys

from flask import Flask, render_template, request

# 将项目根目录加入 path 以便导入 analysis 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

app = Flask(__name__)

ENGINE = create_engine(
    "mysql+pymysql://crawler:123456@127.0.0.1:3306/douban_movie?charset=utf8mb4"
)

ANALYSIS_OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "analysis", "output"
)


def query(sql, **params):
    with ENGINE.connect() as conn:
        result = conn.execute(text(sql), params)
        return [dict(row._mapping) for row in result]


# ============================================================
# Routes
# ============================================================


@app.route("/")
def index():
    """首页仪表盘"""
    stats = {}
    stats["total_movies"] = query("SELECT COUNT(*) AS cnt FROM movie")[0]["cnt"]
    stats["total_comments"] = query("SELECT COUNT(*) AS cnt FROM comment")[0]["cnt"]
    stats["total_reviews"] = query("SELECT COUNT(*) AS cnt FROM review")[0]["cnt"]
    stats["avg_score"] = query(
        "SELECT ROUND(AVG(douban_score), 2) AS val FROM movie WHERE douban_score IS NOT NULL"
    )[0]["val"]
    stats["total_genres"] = query(
        "SELECT COUNT(DISTINCT genre_name) AS cnt FROM movie_genre"
    )[0]["cnt"]

    # 最近添加的电影
    recent_movies = query(
        "SELECT movie_id, movie_name, douban_score, rating_count "
        "FROM movie ORDER BY crawl_time DESC LIMIT 10"
    )

    return render_template("index.html", stats=stats, recent_movies=recent_movies)


@app.route("/movies")
def movie_list():
    """电影列表 (分页 + 搜索)"""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "", type=str)
    per_page = 20
    offset = (page - 1) * per_page

    if search:
        count_sql = "SELECT COUNT(*) AS cnt FROM movie WHERE movie_name LIKE :kw"
        data_sql = (
            "SELECT movie_id, movie_name, douban_score, rating_count, country, release_date "
            "FROM movie WHERE movie_name LIKE :kw "
            "ORDER BY douban_score DESC LIMIT :limit OFFSET :offset"
        )
        kw = f"%{search}%"
        total = query(count_sql, kw=kw)[0]["cnt"]
        movies = query(data_sql, kw=kw, limit=per_page, offset=offset)
    else:
        count_sql = "SELECT COUNT(*) AS cnt FROM movie"
        data_sql = (
            "SELECT movie_id, movie_name, douban_score, rating_count, country, release_date "
            "FROM movie ORDER BY douban_score DESC LIMIT :limit OFFSET :offset"
        )
        total = query(count_sql)[0]["cnt"]
        movies = query(data_sql, limit=per_page, offset=offset)

    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        "movie_list.html",
        movies=movies,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
    )


@app.route("/movies/<int:movie_id>")
def movie_detail(movie_id):
    """电影详情页"""
    movie = query("SELECT * FROM movie WHERE movie_id = :mid", mid=movie_id)
    if not movie:
        return "电影不存在", 404
    movie = movie[0]

    persons = query(
        "SELECT person_name, role FROM movie_person WHERE movie_id = :mid", mid=movie_id
    )
    genres = query(
        "SELECT genre_name FROM movie_genre WHERE movie_id = :mid", mid=movie_id
    )
    comments = query(
        "SELECT nickname, content, useful_num, comment_time "
        "FROM comment WHERE movie_id = :mid ORDER BY useful_num DESC LIMIT 20",
        mid=movie_id,
    )

    return render_template(
        "movie_detail.html",
        movie=movie,
        persons=persons,
        genres=[g["genre_name"] for g in genres],
        comments=comments,
    )


@app.route("/analysis")
def analysis():
    """分析图表展示页"""
    # 列出可用的图表 HTML 文件
    charts = []
    if os.path.isdir(ANALYSIS_OUTPUT_DIR):
        for f in sorted(os.listdir(ANALYSIS_OUTPUT_DIR)):
            if f.endswith(".html"):
                name = f.replace(".html", "").replace("_", " ").title()
                charts.append({"name": name, "file": f})

    return render_template("analysis.html", charts=charts)


if __name__ == "__main__":
    print("Starting Flask server at http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
