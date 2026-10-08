# OverCome 插件目录

本目录存放 OverCome 的**构建期插件**（构建在本地或 GitHub Actions 执行，无服务器运行时）。

## 快速开始

```bash
plugins/
└── my-plugin/            # 一个插件一个目录（目录名即插件 id）
    ├── plugin.json       # 元数据（必填）
    └── plugin.py         # Python 入口（可选）
```

在 `config.json` 中开启：

```json
"plugins": { "enabled": true, "path": "plugins" }
```

## 可用插件

| 插件 | 版本 | 说明 |
| --- | --- | --- |
| [daily-quote](./daily-quote/) | v1.0.0 | 演示插件：右侧栏「每日一言」组件 + 文章页底部随机引用（widget / process 钩子示例） |

## 钩子一览

| 钩子 | 签名 | 作用 |
| --- | --- | --- |
| `process` | `process(html, context) -> html` | 逐页构建后处理 |
| `widget` | `widget(context) -> str` | 右侧栏自定义组件 |
| `register_pages` | `register_pages() -> [(path, html)]` | 构建期注册额外静态页面 |

完整开发文档见站点文档页 `content/docs/plugin-dev.md`（构建后为 `/docs/plugin-dev/`）。

## 安全提示

插件在构建机器本地运行，**只安装 / 信任你自己编写的插件**；不要从不可信来源下载插件后直接构建。