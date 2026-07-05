"""
清理数据库中无评分的电影及相关子表数据。

运行方式:
    cd douban_movie_system
    python cleanup_data.py

安全特性: 默认 dry-run 模式，确认后再加 --commit 执行删除。
"""

import argparse
import sys

import pymysql

CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "crawler",
    "password": "123456",
    "database": "douban_movie",
    "charset": "utf8mb4",
}


def main(commit: bool = False):
    conn = pymysql.connect(**CONFIG)
    cursor = conn.cursor()

    # 查找无评分的电影
    cursor.execute(
        "SELECT movie_id, movie_name FROM movie "
        "WHERE douban_score IS NULL OR movie_name IS NULL OR movie_name = ''"
    )
    bad_movies = cursor.fetchall()

    if not bad_movies:
        print("数据库状态良好，无需清理。")
        cursor.close()
        conn.close()
        return

    print(f"发现 {len(bad_movies)} 部数据不完整的电影:")
    for mid, name in bad_movies[:20]:
        print(f"  [{mid}] {name or '(无名称)'}")
    if len(bad_movies) > 20:
        print(f"  ... 等 {len(bad_movies) - 20} 部")

    if not commit:
        print(f"\n[DRY RUN] 以上共 {len(bad_movies)} 条记录将被删除。")
        print("确认删除请加 --commit 参数。")
        cursor.close()
        conn.close()
        return

    # 执行删除 (先删子表再删主表)
    ids = [m[0] for m in bad_movies]
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        placeholders = ",".join(["%s"] * len(chunk))

        cursor.execute(
            f"DELETE FROM movie_person WHERE movie_id IN ({placeholders})", chunk
        )
        cursor.execute(
            f"DELETE FROM movie_genre WHERE movie_id IN ({placeholders})", chunk
        )
        cursor.execute(
            f"DELETE FROM comment WHERE movie_id IN ({placeholders})", chunk
        )
        cursor.execute(
            f"DELETE FROM review WHERE movie_id IN ({placeholders})", chunk
        )
        cursor.execute(
            f"DELETE FROM movie WHERE movie_id IN ({placeholders})", chunk
        )

    conn.commit()

    # 统计清理后的数据
    cursor.execute("SELECT COUNT(*) FROM movie")
    remaining = cursor.fetchone()[0]
    cursor.execute("SELECT ROUND(AVG(douban_score), 2) FROM movie WHERE douban_score IS NOT NULL")
    avg = cursor.fetchone()[0]

    print(f"\n清理完成。")
    print(f"  删除: {len(bad_movies)} 部电影")
    print(f"  剩余: {remaining} 部电影")
    print(f"  平均分: {avg}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理豆瓣电影数据库中的低质量数据")
    parser.add_argument("--commit", action="store_true", help="确认执行删除 (默认 dry-run)")
    args = parser.parse_args()
    main(commit=args.commit)
