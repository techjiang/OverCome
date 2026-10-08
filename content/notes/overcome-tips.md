---
title: OverCome 使用技巧速记
date: 2026-10-08
tags: [OverCome, 笔记]
summary: 关于 OverCome 的写作、配置与部署技巧，持续更新。
---

## 写作

- 文章放在 `content/posts/`，文件名以 `YYYY-MM-DD-` 开头会自动识别日期。
- 置顶：在 front matter 写 `pinned: true`，文章会排到首页最前并显示 📌 徽标。
- 精选：`featured: true` 会出现在首页精选区。

## 配置

所有站点级设置都在 `config.json`：

| 配置项 | 作用 |
| --- | --- |
| `site.posts_per_page` | 首页每页文章数 |
| `layout.card_cover_height` | 文章卡片封面高度 |
| `layout.content_max_width` | 正文最大宽度 |
| `link_strategy` | 站内/站外链接跳转方式 |

## 部署

任何提交推到 `main` 分支都会触发 GitHub Actions 自动构建并发布到 Pages。