---
title: 三步将 OverCome 部署到 GitHub Pages
date: 2026-10-05
tags: [GitHub, 部署, 教程]
category: 教程
summary: 从 Fork 到上线只需三分钟：配置仓库、启用 Actions、推送到 main。本文手把手演示完整部署流程。
---

OverCome 的全部构建逻辑都在一个零依赖的 `build.py` 中，部署则完全依赖 GitHub Actions——所以你只需要一个 GitHub 账号即可。

## 第一步：准备仓库

将本仓库 Fork 到自己的账号，或者直接新建一个仓库并把代码推送上去。

在仓库 **Settings → Pages** 中确认：

1. Source 选择 **GitHub Actions**
2. 不需要自定义域名也可以直接使用 `https://<用户名>.github.io/<仓库名>/`

## 第二步：改配置

编辑根目录的 `config.json`，把站点信息换成你自己的：

```json
{
  "site": {
    "title": "我的博客",
    "description": "在这里用一句话介绍自己",
    "author": "你的名字",
    "base": "https://你的用户名.github.io/你的仓库名/"
  }
}
```

> 注意 `base` 必须以 `/` 结尾，它是生成订阅源与站点地图的完整地址。

## 第三步：推送上线

提交并推送，剩下交给自动化：

```bash
git add .
git commit -m "feat: 初始化博客"
git push origin main
```

[.github/workflows/deploy.yml](https://github.com/techjiang/OverCome) 中定义的流水线会自动执行 `build.py` 并把 `dist/` 部署到 Pages，通常 **1~2 分钟**后即可访问。

## 常见问题

**Q：发布后没生效？**
检查 Actions 页面工作流是否成功，以及 Settings → Pages 是否选择了 "GitHub Actions" 作为 Source。

**Q：如何修改每页文章数？**
`config.json` 中的 `posts_per_page` 字段，默认 6 篇。

**Q：如何升级主题？**
主题源码位于 `theme/` 目录，CSS 与 JS 全部开源可改，改完推送即可。