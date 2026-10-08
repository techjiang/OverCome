---
title: 主题定制指南：把莫兰迪粉换成你的调性
date: 2026-09-20
tags: [主题, CSS]
category: 教程
summary: OverCome 主题采用 CSS 变量与「固定侧栏」布局，换肤只需改十几个颜色值。本文带你快速摸清主题结构与定制方法。
---

OverCome 默认主题是一套克制的**莫兰迪粉**配色：低饱和的粉与奶油底色，配合桌面端固定侧栏、移动端抽屉导航。所有视觉参数都收敛在 CSS 变量里，换肤非常简单。

## 主题的文件结构

```
theme/
├── templates/
│   └── base.html        # 站点骨架：侧栏、导航、页脚
├── static/
│   ├── css/
│   │   ├── style.css    # 全部样式与主题变量
│   │   └── highlight.css
│   └── js/
│       ├── main.js      # 深色模式、侧栏、高亮、复制
│       └── search.js    # 站内搜索
```

## 快速换肤：改 CSS 变量

打开 `theme/static/css/style.css`，顶部 `:root` 块就是整套色板：

```css
:root {
  --bg: #faf7f5;          /* 页面背景 */
  --card: #ffffff;        /* 卡片背景 */
  --text: #3c3633;        /* 正文颜色 */
  --accent: #c98a8a;      /* 主强调色 */
  --accent-grad: linear-gradient(135deg, #e9b0b0, #b98cc9); /* 品牌渐变 */
}
```

想换成清爽的蓝绿调，把 `--accent`、`--accent-grad` 与右侧 `html.dark` 块中的对应项替换即可，全站配色会同步更新。

## 布局与响应式

桌面端采用 **固定侧栏** 布局：侧栏 `position: sticky` 常驻视口，正文区独立滚动；窄屏（≤900px）自动切换为顶部条 + 抽屉导航。

```css
.layout { grid-template-columns: var(--sidebar-w) 1fr; }
@media (max-width: 900px) { .layout { display: flex; flex-direction: column; } }
```

- 想改侧栏宽度 → 修改 `--sidebar-w`（默认 264px）
- 想改圆角 → 修改 `--radius`
- 想换字体 → 修改 `--font-serif` / `--font-sans`

## 构建与预览

任何改动都直接刷新即得：

```bash
python3 build.py        # 重新生成站点
cd dist && python3 -m http.server 8080
```

主题文件在 `theme/` 目录，与内容、配置相互独立，可以放心折腾——坏了随时用 `git restore` 回滚。