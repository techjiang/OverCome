---
title: 插件开发指南
date: 2026-10-08
category: 进阶教程
summary: OverCome 插件生态从零到一：目录规范、plugin.json 元数据、process / widget / register_pages 三大钩子，以及侧边栏组件自定义机制。
---

## 插件是什么

OverCome 是无服务器静态博客，但构建是在本地（或 GitHub Actions）执行的。**插件生态**利用构建期能力，让你给站点注入动态行为，不引入后端：

- 在右侧栏渲染自定义组件（每日一言、天气、订阅卡片…）
- 对每个页面做构建期后处理（追加引用、注入脚本、改写 HTML…）
- 注册全新的静态页面（镜像页、工具页、API 文档站…）

插件在**构建机器本地运行**，只安装/信任你自己编写的插件。

## 目录规范

```
plugins/
└── my-plugin/          ← 一个插件一个目录（目录名即插件 id）
    ├── plugin.json     ← 元数据（必填）
    └── plugin.py       ← Python 入口（可选，取决于使用哪些钩子）
```

仓库根目录 `config.json` 控制开关：

```json
"plugins": { "enabled": true, "path": "plugins" }
```

## plugin.json 元数据

```json
{
  "name": "我的插件",
  "version": "1.0.0",
  "description": "一句话说明这个插件做什么",
  "author": "科技酱",
  "entry": "plugin.py",
  "registry": true
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 否 | 展示名，缺省用目录名 |
| `version` | 否 | 版本号，缺省 `0.1.0` |
| `description` | 否 | 插件注册表页展示的简介 |
| `author` | 否 | 作者，缺省取 `config.site.author` |
| `entry` | 否 | Python 入口文件名，缺省 `plugin.py` |
| `registry` | 否 | 是否出现在 `/plugins/` 注册表页，默认展示 |

## 三大钩子

### 1) `process(html, context) -> str` —— 逐页后处理

每个页面构建完成后调用，返回修改后的 HTML。适合“在文章底部追加内容、注入脚本、替换标记”。

```python
def process(html, context):
    # context: {page_type, root, title}
    #   page_type: home / archive / tags / category / post / doc / note / page / links / search / dynamic / plugins / ...
    if context.get("page_type") not in ("post", "doc", "note"):
        return html
    quote = '<blockquote class="plugin-tail-quote">“先完成，再完美。”</blockquote>'
    return html.replace('<footer class="post-footer">', quote + '<footer class="post-footer">', 1)
```

> 署名（`.powered-by`）受保护，**不要**在 process 钩子里删除、修改、遮掩它。

### 2) `widget(context) -> str` —— 右侧栏组件

返回一段 HTML，构建器会自动包上 `.widget` 容器。先在页面配置里挂载：

```json
"sidebar_right": { "pages": { "home": { "widgets": ["latest", "plugin:my-plugin"] } } }
```

```python
def widget(context):
    # context: {root, page_type}
    return (
        '<h3>我的组件</h3>'
        '<p class="custom-widget-text">插件渲染的侧栏组件内容。</p>'
    )
```

组件里若出现 `<script>`，注意静态页脚本无法访问构建期变量——请把数据渲染成 HTML/JSON 再交给前端脚本。

### 3) `register_pages() -> [(path, html)]` —— 构建期注册页面

返回 `(路径, 完整 HTML)` 列表，构建时写入站点。路径相对站点根，如 `"tools/pinyin/"`。

```python
def register_pages():
    html = "<html><body><h1>插件自建页面</h1></body></html>"
    return [("tools/my-tool/", html)]
```

> 自建页面不会自动打上署名与站点头尾样式；想复用主题外壳请使用 `Renderer`（见 `build.py`）或参考已有页面的结构。

## 侧边栏组件自定义机制

右侧栏每个组件都是 `sidebar_right.pages.<页面类型>.widgets` 数组里的一项，**顺序即渲染顺序**，内置组件与自定义组件可混排：

| 写法 | 类型 | 说明 |
| --- | --- | --- |
| `latest` / `tags` / `archive` / `monitor` / `related` | 内置 | 最新文章 / 标签云 / 归档 / 站点监测 / 相关阅读 |
| `custom:about` | 配置组件 | 对应 `config.custom_widgets` 中 `id` 为 `about` 的组件 |
| `plugin:my-plugin` | 插件组件 | 调用 `my-plugin` 的 `widget()` 钩子 |
| `toc` | 内置 | 文章目录（自动追加） |

`config.custom_widgets` 支持三种内置型别，无需写插件：

```json
"custom_widgets": [
  { "id": "about", "title": "关于本站", "type": "html", "html": "<p>…</p>" },
  { "id": "slogan", "title": "一句话", "type": "text", "text": "写下来，才能想清楚。" },
  { "id": "nav",   "title": "快捷导航", "type": "list", "items": [
      { "label": "GitHub", "url": "https://github.com/techjiang/OverCome" }
  ]}
]
```

然后把 id 挂到任意页面类型的 widgets 里（如 `"custom:about"`）即可。

## 调试与发布

1. 在仓库根目录运行 `python3 build.py`，观察输出 `[OK] 插件: N 个已加载`。
2. 打开本地 `dist/` 验证插件组件与页面。
3. 插件页 `/plugins/` 会自动汇总展示所有注册的插件（含能力标签）。

## 既有参考实现

- `plugins/daily-quote/` —— 官方示例：同时演示 `widget()` 与 `process()` 两个钩子。

## 进阶：插件能做到什么

由于钩子收到的是完整 HTML 与构建上下文，插件理论上可以实现：

- 静态表单提交到第三方服务（FORM 直发 webhook）
- 从本地 JSON 生成数据页 / 工具页
- 注入自定义 JS/CSS（比如评论区脚本、站点统计）
- 按文章元数据生成索引 / 知识图谱

插件生态是“聪明地借用构建期”，不要试图在纯静态里塞需要后端的逻辑（登录、持久化写库等），那些场景请配合第三方无服务器服务。