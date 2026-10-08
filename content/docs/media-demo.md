---
title: 媒体查看与链接演示
date: 2026-10-08
category: 使用指南
summary: 图片灯箱缩放、视频/PDF/文档在线查看、站内站外链接跳转策略的演示页面。
---

## 图片灯箱

点击下方图片即可打开灯箱：支持 **滚轮/按钮缩放、拖动平移、方向键切换、双击复位**。

![山景演示图](../../static/img/demo-mountain.svg)

![落日海岸演示图](../../static/img/demo-sunset.svg)

> 多图页面会自动进入「上一项 / 下一项」切换模式。

## 视频在线查看

点击外部视频链接即可在灯箱内播放，原生播放器提供**播放进度、音量与全屏**控制：

- [示例视频：花朵绽放 (MP4)](https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4)

> 也可以直接在正文嵌入 `<video>`，同样会在灯箱中放大查看。

## PDF 在线查看

点击 PDF 链接使用浏览器原生查看器预览，支持**缩放、翻页、进度**：

- [W3C 测试文档 (PDF)](https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf)

## Office 文档

Word / Excel / PPT 等 Office 文件（`.doc`、`.docx`、`.xls`、`.xlsx`、`.ppt`、`.pptx`）链接同样会进入灯箱，通过浏览器原生或在线预览服务查看。

> 预览要求文件为**公开可访问**的 URL；私有文件请直接下载后在本地打开。

## 链接跳转策略

- **站内链接**（如 [快速开始](../quickstart/)）→ 当前页直接跳转
- **站外链接**（如 [GitHub](https://github.com/techjiang)）→ 自动在新标签页打开