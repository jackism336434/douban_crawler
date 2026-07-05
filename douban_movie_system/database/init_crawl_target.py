"""
初始化 crawl_target 表。

运行方式:
    cd douban_movie_system
    python database/init_crawl_target.py
"""

import pymysql

CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "crawler",
    "password": "123456",
    "database": "douban_movie",
    "charset": "utf8mb4",
}

SQL = """
CREATE TABLE IF NOT EXISTS crawl_target (
    id INT AUTO_INCREMENT PRIMARY KEY,
    target_name VARCHAR(100) NOT NULL COMMENT '类型或主题名称',
    target_type ENUM('genre', 'tag', 'keyword') DEFAULT 'genre' COMMENT '目标类型',
    status ENUM('idle', 'pending', 'running', 'done') DEFAULT 'idle' COMMENT '爬取状态',
    last_crawl_time DATETIME COMMENT '最近一次爬取时间',
    movie_count INT DEFAULT 0 COMMENT '本次爬取到的电影数',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_target_name (target_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='爬取目标管理表';
"""

SEED_GENRES = [
    "剧情", "喜剧", "动作", "爱情", "科幻", "悬疑", "惊悚", "恐怖",
    "动画", "纪录片", "短片", "音乐", "歌舞", "历史", "战争",
    "犯罪", "奇幻", "冒险", "武侠", "家庭", "传记",
]

# 禁止爬取的标签
BLOCKED_TAGS = {"情色", "色情", "成人"}


def main():
    conn = pymysql.connect(**CONFIG)
    cursor = conn.cursor()

    # Create table
    cursor.execute(SQL)
    print("Table crawl_target created (or already exists).")

    # Seed with common genres if table is empty
    cursor.execute("SELECT COUNT(*) FROM crawl_target")
    if cursor.fetchone()[0] == 0:
        for genre in SEED_GENRES:
            cursor.execute(
                "INSERT IGNORE INTO crawl_target (target_name, target_type, status) "
                "VALUES (%s, 'genre', 'idle')",
                (genre,),
            )
        conn.commit()
        print(f"Seeded {len(SEED_GENRES)} default genres.")

    # Show current state
    cursor.execute("SELECT id, target_name, target_type, status, movie_count FROM crawl_target ORDER BY id")
    rows = cursor.fetchall()
    print(f"\nCurrent crawl targets ({len(rows)}):")
    for row in rows:
        print(f"  [{row[0]}] {row[1]} ({row[2]}) — {row[3]} | {row[4]} movies")

    cursor.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
