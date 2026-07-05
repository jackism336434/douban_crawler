"""
豆瓣电影数据展示系统 (Flask)

运行方式:
    cd douban_movie_system
    python web/app.py
    # 浏览器打开 http://localhost:5000
"""

import os
import re
import sys
import json
import subprocess
import time
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, jsonify

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

# ── Crawl job tracking ────────────────────────────────────────
CRAWL_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(CRAWL_LOG_DIR, exist_ok=True)

_crawl_job = {
    "running": False,
    "pid": None,
    "started_at": None,
    "log_file": None,
    "spider": None,
}


def _get_log_tail(log_file, lines=40):
    """Return the last N lines of a log file."""
    if not log_file or not os.path.exists(log_file):
        return ""
    with open(log_file, "r", errors="replace") as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])


def query(sql, **params):
    with ENGINE.connect() as conn:
        result = conn.execute(text(sql), params)
        return [dict(row._mapping) for row in result]


def execute(sql, **params):
    """执行写操作 (INSERT/UPDATE/DELETE)，返回 affected row count"""
    with ENGINE.begin() as conn:
        result = conn.execute(text(sql), params)
        return result.rowcount


# ============================================================
# Routes
# ============================================================


@app.route("/")
def index():
    """首页仪表盘"""
    stats = {}
    stats["total_movies"] = query(
        "SELECT COUNT(*) AS cnt FROM movie WHERE movie_name IS NOT NULL AND movie_name != ''"
    )[0]["cnt"]
    stats["total_comments"] = query("SELECT COUNT(*) AS cnt FROM comment")[0]["cnt"]
    stats["total_reviews"] = query("SELECT COUNT(*) AS cnt FROM review")[0]["cnt"]
    stats["avg_score"] = query(
        "SELECT ROUND(AVG(douban_score), 2) AS val FROM movie WHERE douban_score IS NOT NULL"
    )[0]["val"]
    stats["total_genres"] = query(
        "SELECT COUNT(DISTINCT genre_name) AS cnt FROM movie_genre"
    )[0]["cnt"]

    # 最近添加的电影（有评论或影评的优先，只显示有评分的）
    recent_movies = query(
        "SELECT movie_id, movie_name, douban_score, rating_count "
        "FROM movie WHERE douban_score IS NOT NULL "
        "ORDER BY (EXISTS(SELECT 1 FROM comment c WHERE c.movie_id = movie.movie_id) "
        "OR EXISTS(SELECT 1 FROM review r WHERE r.movie_id = movie.movie_id)) DESC, "
        "crawl_time DESC LIMIT 10"
    )

    return render_template("index.html", stats=stats, recent_movies=recent_movies)


@app.route("/movies")
def movie_list():
    """电影列表 (分页 + 搜索)"""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "", type=str)
    per_page = 20
    offset = (page - 1) * per_page

    base_filter = "WHERE douban_score IS NOT NULL"
    # 有评论或影评的电影排在前面
    order_clause = (
        "ORDER BY (EXISTS(SELECT 1 FROM comment c WHERE c.movie_id = movie.movie_id) "
        "OR EXISTS(SELECT 1 FROM review r WHERE r.movie_id = movie.movie_id)) DESC, "
        "douban_score DESC"
    )
    if search:
        count_sql = (
            f"SELECT COUNT(*) AS cnt FROM movie {base_filter} AND movie_name LIKE :kw"
        )
        data_sql = (
            "SELECT movie_id, movie_name, douban_score, rating_count, country, release_date "
            f"FROM movie {base_filter} AND movie_name LIKE :kw "
            f"{order_clause} LIMIT :limit OFFSET :offset"
        )
        kw = f"%{search}%"
        total = query(count_sql, kw=kw)[0]["cnt"]
        movies = query(data_sql, kw=kw, limit=per_page, offset=offset)
    else:
        count_sql = f"SELECT COUNT(*) AS cnt FROM movie {base_filter}"
        data_sql = (
            "SELECT movie_id, movie_name, douban_score, rating_count, country, release_date "
            f"FROM movie {base_filter} "
            f"{order_clause} LIMIT :limit OFFSET :offset"
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
    reviews = query(
        "SELECT nickname, content, useful_num, useless_num, reply_num, review_time "
        "FROM review WHERE movie_id = :mid ORDER BY useful_num DESC LIMIT 10",
        mid=movie_id,
    )

    # Count of actually scraped comments/reviews
    scraped_comment = query(
        "SELECT COUNT(*) AS cnt FROM comment WHERE movie_id = :mid", mid=movie_id
    )[0]["cnt"]
    scraped_review = query(
        "SELECT COUNT(*) AS cnt FROM review WHERE movie_id = :mid", mid=movie_id
    )[0]["cnt"]

    return render_template(
        "movie_detail.html",
        movie=movie,
        persons=persons,
        genres=[g["genre_name"] for g in genres],
        comments=comments,
        reviews=reviews,
        scraped_comment_count=scraped_comment,
        scraped_review_count=scraped_review,
    )


@app.route("/movies/<int:movie_id>/crawl-content", methods=["POST"])
def crawl_movie_content(movie_id):
    """为单部电影启动短评 + 影评爬虫"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(CRAWL_LOG_DIR, f"crawl_content_{movie_id}_{timestamp}.log")

        proc = subprocess.Popen(
            [
                "scrapy", "crawl", "comment",
                "-a", f"movie_ids={movie_id}",
                "-a", "max_pages=3",
                "--logfile", log_file,
                "-L", "INFO",
            ],
            cwd=SPIDER_SCRIPT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Also launch review spider in parallel
        log_file_r = os.path.join(CRAWL_LOG_DIR, f"crawl_review_{movie_id}_{timestamp}.log")
        proc_r = subprocess.Popen(
            [
                "scrapy", "crawl", "review",
                "-a", f"movie_ids={movie_id}",
                "-a", "max_pages=2",
                "--logfile", log_file_r,
                "-L", "INFO",
            ],
            cwd=SPIDER_SCRIPT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        return jsonify({"ok": True, "pid": proc.pid})

    except FileNotFoundError:
        return jsonify({"ok": False, "error": "scrapy 命令未找到，请确认已激活虚拟环境"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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


# ============================================================
# Crawl Target Management
# ============================================================


@app.route("/targets")
def crawl_targets():
    """爬取目标管理页"""
    msg = request.args.get("msg", "")
    error = request.args.get("error", "")

    try:
        targets = query(
            "SELECT id, target_name, target_type, status, movie_count, "
            "last_crawl_time, created_at "
            "FROM crawl_target ORDER BY id"
        )
    except Exception:
        # 表不存在
        return render_template(
            "crawl_targets.html",
            targets=[],
            target_count=0,
            done_count=0,
            suggestions=[],
            msg="",
            error="crawl_target 表尚未创建。请先运行: python database/init_crawl_target.py",
        )

    # 统计各状态的电影数
    target_count = len(targets)
    done_count = sum(1 for t in targets if t["status"] == "done")

    # 已有的 genre 不在目标中的 (可用于建议)
    existing_genres = query(
        "SELECT DISTINCT genre_name FROM movie_genre ORDER BY genre_name"
    )
    existing_names = {g["genre_name"] for g in existing_genres}
    target_names = {t["target_name"] for t in targets}
    suggestions = sorted(existing_names - target_names)

    return render_template(
        "crawl_targets.html",
        targets=targets,
        target_count=target_count,
        done_count=done_count,
        suggestions=suggestions,
        msg=msg,
        error=error,
    )


@app.route("/targets/add", methods=["POST"])
def crawl_targets_add():
    """添加爬取目标"""
    target_name = request.form.get("target_name", "").strip()
    target_type = request.form.get("target_type", "genre")

    if not target_name:
        return redirect(url_for("crawl_targets", error="名称不能为空"))

    # 过滤不适宜标签
    BLOCKED = {"情色", "色情", "成人"}
    if target_name in BLOCKED:
        return redirect(url_for("crawl_targets", error=f"「{target_name}」不在允许范围内"))

    try:
        execute(
            "INSERT INTO crawl_target (target_name, target_type) VALUES (:name, :type)",
            name=target_name,
            type=target_type,
        )
        return redirect(url_for("crawl_targets", msg=f"已添加：{target_name}"))
    except Exception as e:
        err = str(e)
        if "Duplicate" in err:
            return redirect(url_for("crawl_targets", error=f"「{target_name}」已存在"))
        return redirect(url_for("crawl_targets", error=err))


@app.route("/targets/<int:target_id>/delete", methods=["POST"])
def crawl_targets_delete(target_id):
    """删除爬取目标"""
    target = query("SELECT target_name FROM crawl_target WHERE id = :tid", tid=target_id)
    if not target:
        return redirect(url_for("crawl_targets", error="目标不存在"))

    name = target[0]["target_name"]
    execute("DELETE FROM crawl_target WHERE id = :tid", tid=target_id)
    return redirect(url_for("crawl_targets", msg=f"已删除：{name}"))


@app.route("/targets/<int:target_id>/reset", methods=["POST"])
def crawl_targets_reset(target_id):
    """重置爬取状态为 pending"""
    execute(
        "UPDATE crawl_target SET status = 'pending' WHERE id = :tid", tid=target_id
    )
    return redirect(url_for("crawl_targets", msg="状态已重置"))


# ============================================================
# Crawl Trigger (subprocess-based)
# ============================================================

SPIDER_SCRIPT = os.path.join(os.path.dirname(__file__), "..")


@app.route("/targets/crawl", methods=["POST"])
def crawl_trigger():
    """启动爬虫（后台子进程）"""
    global _crawl_job

    if _crawl_job["running"]:
        # Check if the process is still alive
        pid = _crawl_job.get("pid")
        if pid:
            try:
                os.kill(pid, 0)  # Does not kill, just checks existence
                return redirect(
                    url_for("crawl_targets", error="爬虫正在运行中，请等待完成")
                )
            except OSError:
                _crawl_job["running"] = False

    spider = request.form.get("spider", "tag_movie")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(CRAWL_LOG_DIR, f"crawl_{spider}_{timestamp}.log")

    # Mark pending targets as running
    try:
        execute("UPDATE crawl_target SET status = 'pending' WHERE status = 'idle'")
    except Exception:
        pass

    # Spawn scrapy in background
    try:
        proc = subprocess.Popen(
            ["scrapy", "crawl", spider, "--logfile", log_file, "-L", "INFO"],
            cwd=SPIDER_SCRIPT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        return redirect(
            url_for("crawl_targets",
                    error="scrapy 命令未找到。请确认已激活虚拟环境并安装依赖。")
        )

    _crawl_job = {
        "running": True,
        "pid": proc.pid,
        "started_at": timestamp,
        "log_file": log_file,
        "spider": spider,
    }

    return redirect(
        url_for("crawl_targets", msg=f"爬虫 {spider} 已启动 (PID: {proc.pid})")
    )


@app.route("/targets/crawl/status")
def crawl_status():
    """返回爬虫运行状态 (JSON)"""
    global _crawl_job
    job = dict(_crawl_job)

    if job["running"] and job.get("pid"):
        try:
            os.kill(job["pid"], 0)
        except OSError:
            job["running"] = False
            _crawl_job["running"] = False

    log_tail = _get_log_tail(job.get("log_file"), lines=30)

    # Parse progress from log
    progress = ""
    if log_tail:
        m = re.search(r"Scraped (\d+) movies", log_tail)
        if m:
            progress = f"已采集 {m.group(1)} 部电影"

    return jsonify({
        "running": job["running"],
        "pid": job.get("pid"),
        "spider": job.get("spider"),
        "started_at": job.get("started_at"),
        "progress": progress,
        "log_tail": log_tail,
    })


if __name__ == "__main__":
    print("Starting Flask server at http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
