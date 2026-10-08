---
title: 快速开始
date: 2026-10-08
category: 使用指南
summary: 三分钟上手 OverCome：安装、写作、部署到 GitHub Pages。
---

## 什么是 OverCome

OverCome 是运行在 **GitHub Pages** 上的无服务器免费博客系统：无需数据库、无需后端，纯静态却功能齐全。

### 核心特性

- 零依赖：只需 `python3 build.py` 一键构建
- 完整内容体系：文章、文档、自定义页面、友链、问卷表单
- 高级能力：全文搜索、深色模式、置顶与封面文章、短链接
- 顶级 SEO：自动生成 sitemap.xml 与 feed.xml

## 快速上手

1. 把内容写进 `content/posts/`，使用 Markdown 语法
2. 运行 `python3 build.py` 生成 `dist/`
3. 推送 `main` 分支，GitHub Actions 自动构建并部署

## 常用目录

| 目录 | 作用 |
| --- | --- |
| `content/posts/` | 博客文章 |
| `content/docs/` | 文档（自动生成目录页） |
| `content/pages/` | 独立页面（`.html` 文件原样透传） |
| `config.json` | 站点配置、导航、友链、短链接、表单 |

更多细节请查阅「部署指南」文章。