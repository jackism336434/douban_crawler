# 豆瓣电影信息采集与分析系统

面向豆瓣电影的网络爬虫系统，实现电影基本信息、评分、短评与影评的自动采集、存储、分析与 Web 展示。

## 项目概述

- **开发语言**: Python 3.11
- **爬虫框架**: Scrapy 2.11
- **数据库**: MySQL 8.0 + Redis 7
- **数据分析**: Pandas + pyecharts
- **Web 展示**: Flask + 自主设计「Film Archive」前端

## 系统架构

```
种子 URL (Top250)              爬取目标管理 (crawl_target 表)
     │                                    │
     ▼                                    ▼
电影列表爬虫 ──→ 电影详情爬虫         标签爬虫 (tag_movie)
     │              │                    │
     │   ┌──────────┼──────────┐        │
     │   ▼          ▼          ▼        ▼
     │ 短评采集   影评采集    (前端一键触发)
     │   │          │                    │
     └───┴──────────┴────────────────────┘
                     ▼
              MySQL 数据库 (7 张表)
                     │
          ┌──────────┼──────────┐
          ▼                     ▼
     数据分析模块           Web 展示系统
  (Pandas + pyecharts)   (Flask + Film Archive)
```

**采集策略**:
- **链式扩展**: 从 Top250 出发，通过推荐列表发现新电影，经两轮扩展覆盖万级数据
- **标签定向**: 从 `crawl_target` 表读取目标类型，访问豆瓣标签页逐类采集
- **前端触发**: Web 界面支持一键启动爬虫，后台 subprocess 运行，实时查看日志

## 数据库设计

7 张核心表：

| 表名 | 用途 | 实际数据量 |
|---|---|---|
| `movie` | 电影基本信息 + 评分 | 67,602 |
| `movie_person` | 导演/编剧/演员关系 | 355,956 |
| `movie_genre` | 类型标签 | 123,673 |
| `comment` | 短评 | 640,667 |
| `review` | 影评 | 25,905 |
| `crawl_log` | 爬虫日志 | — |
| `crawl_target` | 爬取目标管理 | 21（可扩展） |

ER 关系: `movie 1 ─── N movie_person / movie_genre / comment / review`

- 所有子表通过 `movie_id` 外键关联，`ON DELETE CASCADE` 保障一致性
- `comment` 表通过 `(movie_id, nickname, content_hash)` 联合唯一键去重
- `crawl_target` 存储待采集的类型/标签，爬虫启动时读取

## 快速开始

### 环境准备

```bash
# 创建虚拟环境
python3 -m venv venv && source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 启动数据库

```bash
# MySQL
sudo service mysql start    # 数据库 douban_movie, 用户 crawler/123456

# Redis
redis-server
```

### 初始化爬取目标表

```bash
cd douban_movie_system
python database/init_crawl_target.py
```

这会创建 `crawl_target` 表并预填 21 个常见电影类型（剧情、喜剧、科幻、动画…）。

### 导入公开数据集（快速获得数据）

```bash
python import_kaggle.py        # 电影元数据 (67K)
python import_comments_v2.py   # 短评 (640K)
```

### 运行爬虫

```bash
cd douban_movie_system

# ---- 电影采集 ----
scrapy crawl movie -a test=1                # 测试: 5 部
scrapy crawl movie -a max_movies=100         # 100 部
scrapy crawl movie -a max_movies=10000       # 大规模采集

# ---- 标签定向采集 ----
scrapy crawl tag_movie                       # 默认每个标签 100 部
scrapy crawl tag_movie -a per_tag=200        # 每个标签 200 部
scrapy crawl tag_movie -a max_pages=3        # 每个标签最多 3 页
scrapy crawl tag_movie -a test=1             # 测试: 1 个标签

# ---- 短评采集 ----
scrapy crawl comment -a max_movies=10 -a max_pages=5    # 前 10 部热门电影
scrapy crawl comment -a movie_ids=3541415               # 指定电影

# ---- 影评采集 ----
scrapy crawl review -a max_movies=100                   # 前 100 部
scrapy crawl review -a movie_ids=3541415                # 指定电影
```

### 数据清理

```bash
# 删除无评分/无名称的低质量数据
python cleanup_data.py           # dry-run 预览
python cleanup_data.py --commit  # 确认删除
```

### 数据分析与 Web 展示

```bash
# 生成统计图表
python analysis/charts.py

# 启动 Web
python web/app.py
# → http://localhost:5000
```

## Web 功能

| 页面 | 路由 | 功能 |
|---|---|---|
| 总览仪表盘 | `/` | 统计数字 + 最近添加（有评论者优先） |
| 电影列表 | `/movies` | 分页 + 搜索 + 有评论优先排序 |
| 电影详情 | `/movies/<id>` | 基本信息 + 短评 + 影评 + 单部触发采集 |
| 数据分析 | `/analysis` | pyecharts 图表嵌入展示 |
| 爬取管理 | `/targets` | 添加/删除目标 + 一键启动爬虫 + 实时日志 |

## 前端设计

自主设计「**Film Archive**」设计系统，拒绝模板化的 AI 风格：

- **配色**: 纸白 `#fafaf8` + 墨黑 `#1c1c1c` + 投影灯红 `#c1272d`（单点强调）
- **排版**: Noto Serif SC 衬线体（标题/数字/电影名） + 系统无衬线（正文）
- **布局**: 编辑式排版驱动，1px 细线分隔替代卡片阴影，无 emoji 装饰
- **特性**: 响应式（768px / 480px 双断点）、键盘可见焦点、prefers-reduced-motion、打印样式
- **交互**: AJAX 无刷新爬虫触发 + 2 秒轮询状态 + 终端风格实时日志面板

## 反爬策略

豆瓣对爬虫有较强的反爬机制，本项目采用多层对抗：

| 策略 | 实现 |
|---|---|
| User-Agent 轮换 | 10+ 个常见 UA 随机切换 |
| Cookie 注入 | 预置登录态绕过 JS 挑战 |
| 自适应限速 | AutoThrottle — 根据响应延迟自动调整请求间隔 |
| 请求去重 | RedisDupeFilter — 跨重启持久化已抓 URL |
| 失败重试 | RetryMiddleware — 403/418/5xx 自动重试 |
| 黑名单过滤 | `crawl_target` 禁止情色/色情/成人等标签 |

> **注意**: 大规模采集建议使用多账号 Cookie + 代理 IP 轮换。

## 项目结构

```
douban_crawler/
├── douban_movie_system/
│   ├── scrapy.cfg
│   ├── crawler/
│   │   ├── spiders/
│   │   │   ├── movie_spider.py        # 电影爬虫 (Top250 + 推荐链)
│   │   │   ├── tag_spider.py          # 标签爬虫 (crawl_target 驱动)
│   │   │   ├── comment_spider.py      # 短评爬虫
│   │   │   └── review_spider.py       # 影评爬虫
│   │   ├── items.py                   # 数据模型
│   │   ├── pipelines.py               # MySQL 批量写入 + 数据清洗验证
│   │   ├── middlewares.py             # 反爬中间件
│   │   ├── dupefilter.py              # Redis 持久化去重
│   │   └── settings.py                # 爬虫配置
│   ├── database/
│   │   ├── mysql.sql                  # 建表 DDL
│   │   ├── add_crawl_target.sql       # crawl_target 表 DDL
│   │   └── init_crawl_target.py       # 初始化爬取目标表
│   ├── analysis/
│   │   ├── movie_analysis.py          # 数据分析 (Pandas + SQLAlchemy)
│   │   ├── charts.py                  # 图表生成 (pyecharts, Film Archive 配色)
│   │   └── output/                    # 图表 HTML 输出
│   ├── web/
│   │   ├── app.py                     # Flask 应用 (11 条路由)
│   │   └── templates/
│   │       ├── base.html              # Film Archive 设计系统
│   │       ├── index.html             # 总览仪表盘
│   │       ├── movie_list.html        # 电影列表
│   │       ├── movie_detail.html      # 电影详情（短评 + 影评）
│   │       ├── analysis.html          # 数据分析
│   │       └── crawl_targets.html     # 爬取目标管理
│   └── cleanup_data.py                # 数据清理脚本
├── import_kaggle.py                   # Kaggle 数据集导入
├── import_comments_v2.py              # 短评数据集导入
├── generate_report.py                 # 课程设计报告生成
├── requirements.txt
├── dbdesign                           # 数据库设计文档
├── masterplan                         # 项目设计说明书
└── README.md
```

## 数据分析维度

- 评分分布统计
- 电影类型分布
- 国家/地区分布 Top 20
- 导演排行榜（平均评分，≥3 部）
- 高分电影 Top 20
- 上映年份趋势
- 短评 / 影评数量统计

## 课程设计报告

运行以下命令自动生成报告：

```bash
python generate_report.py
# → 豆瓣电影信息采集与分析系统_课程设计报告.docx
```

报告包含封面、摘要、目录、6 章正文（绪论 / 相关技术 / 系统设计 / 系统实现 / 系统测试 / 总结展望）、参考文献和致谢，共 167 段正文 + 6 个数据表格。

## License

本项目仅用于课程学习与研究用途。豆瓣电影数据版权归豆瓣所有。
