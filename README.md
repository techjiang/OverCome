# OverCome

一个运行在 **GitHub Pages** 上的无服务器免费高级博客系统。

零数据库、零后端、零维护成本；纯静态交付，却内置全文搜索、归档、标签云、RSS 订阅、深色模式、语法高亮等完整能力。

## ✨ 特性

- **零依赖构建**：`build.py` 仅用 Python 标准库，任何环境一条命令即可生成整站
- **免费托管**：GitHub Actions 构建 + GitHub Pages 部署，永久免费
- **Markdown 写作**：支持代码块、表格、任务清单、引用等常用语法
- **站内全文搜索**：构建期生成索引，浏览器端即时检索，无需后端
- **分类/标签/归档**：三种聚合视图自动生成
- **RSS 订阅**：Atom 格式 `feed.xml`，与 `sitemap.xml` 一并自动产出
- **深色模式**：跟随系统，可手动切换并记忆偏好
- **响应式主题**：桌面固定侧栏，移动端抽屉导航，莫兰迪粉配色调性
- **阅读体验**：文章目录、阅读时长、上一篇/下一篇、相关阅读、代码复制

## 🚀 快速开始

```bash
# 1. 安装依赖 (无第三方依赖, 仅需 Python 3.8+)
python3 --version

# 2. 构建站点 (输出到 dist/)
python3 build.py

# 3. 本地预览
cd dist && python3 -m http.server 8080
# 打开 http://localhost:8080
```

### 部署到 GitHub Pages

1. 将本仓库推送到你的 GitHub 账号（或直接 Fork）
2. 进入仓库 **Settings → Pages**，将 Source 设为 **GitHub Actions**
3. 修改 `config.json` 中的站点信息（`title`、`description`、`author`、`base`）
4. 推送 `main` 分支，等待工作流完成即可访问

> 工作流位于 `.github/workflows/deploy.yml`，每次推送到 `main` 自动构建部署。

## 📝 写作

在 `content/posts/` 下新建 Markdown 文件：

```markdown
---
title: 我的新文章
date: 2026-10-09
tags: [笔记]
category: 随笔
summary: 会显示在卡片与搜索结果的摘要
---

正文从这里开始。
```

- `content/posts/` — 博客文章，自动按日期排序
- `content/pages/` — 独立页面（如关于页 `about.md`）
- 文件头部 `---` 之间的字段为 front matter（`draft: true` 可暂缓发布）

## 🎨 主题定制

所有外观集中在 `theme/` 目录：

```
theme/
├── templates/base.html    # 页面骨架
└── static/
    ├── css/style.css      # 主题变量 + 全部样式 (换肤改这里)
    └── js/main.js         # 交互逻辑
```

主题使用 CSS 变量组织色板（莫兰迪粉），改动后重新 `python3 build.py` 即可看到效果。

## 📁 目录结构

```
OverCome/
├── build.py               # 静态站点生成器 (零依赖)
├── config.json            # 站点配置
├── content/
│   ├── posts/             # 文章 (Markdown)
│   └── pages/             # 独立页面
├── theme/
│   ├── templates/         # HTML 模板
│   └── static/            # CSS/JS/图片
├── .github/workflows/     # 部署流水线
└── dist/                  # 构建输出 (自动生成, 不入库)
```

## 🔧 技术说明

- 生成器输出：`index.html`、`posts/`、`archive/`、`tags/`、`categories/`、`search/`、`404.html`
- 协议输出：`feed.xml`（Atom）、`sitemap.xml`、`search_index.json`、`robots.txt`
- 所有链接使用相对路径，`config.json` 的 `base` 仅用于生成订阅源/站点地图的绝对地址

## 📄 License

MIT