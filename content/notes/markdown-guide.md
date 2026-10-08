---
title: Markdown 特色语法速查
date: 2026-10-08
tags: [Markdown, 笔记]
summary: OverCome 支持标准 Markdown 之外的增强语法：嵌入卡片、链接卡片、任务列表等。
---

## 标准 Markdown

标题、列表、表格、引用、代码块、行内代码、图片、链接全部支持。

## 增强：链接卡片

独立成行、行首以 `@[` 开头：

```markdown
@[OverCome 源码仓库](https://github.com/techjiang/OverCome)
```

会渲染成带图标与域名的链接卡片，点击跳转。

## 增强：网页嵌入

```markdown
:::embed https://example.com
```

会渲染成可滚动浏览的网页嵌入卡片。

## 增强：任务列表

```markdown
- [x] 完成动态功能
- [ ] 完成插件生态
```

## 数学/代码高亮

代码块自动高亮并提供左上角一键复制。