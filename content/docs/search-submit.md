---
title: 搜索引擎收录与推送指南
date: 2026-10-08
category: 使用指南
summary: 让搜索引擎更快收录你的站点：Bing IndexNow 已自动配置，百度主动推送与必应站长平台验证的回填方法。
---

## 概述

OverCome 已内置完整的 **SEO 基线**：

- `sitemap.xml`：含 `lastmod` / `changefreq` / `priority`，覆盖全部文章、文档与页面
- `feed.xml`：Atom 订阅源，文章全文（`content:encoded`）随源输出
- 每个页面自动生成：`canonical`、Open Graph、Twitter Card、JSON-LD 结构化数据（文章页为 `BlogPosting`，首页为 `WebSite`）
- `robots.txt`：放行全部抓取并声明 Sitemap 位置

搜索引擎收录速度取决于多个因素，但通过下面的自动推送与站长平台验证，Bing 通常可在数天内收录，Google 与百度借助 sitemap 提交也能显著加速。

## Bing IndexNow（已自动配置）

IndexNow 协议无需注册账号，将推送请求发给 `api.indexnow.org` 即可让 Bing 等搜索引擎立即感知新内容。

1. 密钥文件已生成：站点根目录下的 `{key}.txt`（`config.json` 中 `seo.indexnow_key` 字段）
2. 每次部署时，Actions 工作流会自动把最新 URL 列表 POST 到 IndexNow
3. 可手动验证推送是否成功：

```bash
curl "https://api.indexnow.org/indexnow?url=https://techjiang.github.io/OverCome/&key=你的key"
```

返回 `200 OK` 即成功；`403` 表示 key 文件无法访问或匹配。

## 百度主动推送（需回填 token）

百度「普通收录 → 主动推送」可加快百度收录：

1. 打开 [百度搜索资源平台](https://ziyuan.baidu.com/)，用百度账号登录
2. 添加站点：填写 `https://techjiang.github.io/OverCome/`，选择「文件验证」，把百度生成的验证 HTML 文件放入仓库根目录并推送（或使用 CNAME 验证，需先在 Pages 设置自定义域名）
3. 验证通过后进入「普通收录 → 主动推送」，复制你的推送 token
4. 把 token 填入 `config.json` 的 `seo.baidu_token` 字段并推送代码
5. 此后每次部署，Actions 会自动向百度推送最新 URL 列表
6. 也可以手动推送：

```bash
curl -H 'Content-Type:text/plain' --data-binary @urls.txt "https://data.zz.baidu.com/urls?site=https://techjiang.github.io/OverCome/&token=你的token"
```

> 百度对 GitHub Pages 域名的收录有时较慢，建议同时在百度站长平台提交 sitemap 并保持内容更新频率。

## Bing 站长平台（可选，加速 Bing 收录）

1. 访问 [Bing Webmaster Tools](https://www.bing.com/webmasters/)，直接用 Microsoft 账号登录
2. 「添加网站」→ 输入站点地址，选择「XML 文件导入」方式（从 Google Search Console 导入最省事）
3. 也可以验证通过后在后台提交 sitemap：`https://techjiang.github.io/OverCome/sitemap.xml`

## Google 收录（可选）

1. 打开 [Google Search Console](https://search.google.com/search-console/) 并用 Google 账号登录
2. 添加资源 → 选择「网域」或「网址前缀」方式验证（GitHub Pages 一般可用 HTML 文件验证）
3. 在「站点地图」中提交 `https://techjiang.github.io/OverCome/sitemap.xml`

## 常见问题

**为什么 robots.txt 排除了 /go/ 目录？** 短链接落地页只是跳转中转页，不需要被索引，避免重复内容稀释权重。

**为什么 404 页面加了 noindex？** 防止搜索引擎收录无效错误页，影响站点整体质量评分。

**多久会被收录？** Bing IndexNow 推送后通常 1–3 天内收录；百度与 Google 视站点权重与内容质量而定，配合 sitemap 提交通常一周内开始收录。