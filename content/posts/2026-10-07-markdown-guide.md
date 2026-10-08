---
title: Markdown 语法速查：从标题到表格
date: 2026-10-07
tags: [Markdown, 教程]
category: 教程
summary: 一篇覆盖标题、代码块、表格、任务清单等常用语法的 Markdown 参考，也是检验本站渲染能力的完整用例。
---

Markdown 是本站点唯一的写作格式。下面用一份完整用例展示本站支持的语法渲染效果。

## 标题与段落

使用 `#` 到 `######` 表示六级标题，二级、三级标题会自动进入文章目录。

这是一段普通正文，支持 **加粗**、*斜体*、~~删除线~~、`行内代码` 与 [链接](https://github.com)。

## 列表

无序列表：

- 苹果
- 香蕉
  - 香蕉牛奶
  - 香蕉派
- 橙子

有序列表：

1. 打开编辑器
2. 写下想法
3. 推送发布

任务清单：

- [x] 写一篇 Markdown 用例
- [ ] 部署到 GitHub Pages
- [ ] 邀请朋友来读

## 代码块

```python
def hello(name: str) -> str:
    """问候函数示例"""
    message = f"你好, {name}!"
    return message


if __name__ == "__main__":
    print(hello("OverCome"))
```

```bash
# 本地预览构建结果
python3 build.py
cd dist && python3 -m http.server 8080
```

```javascript
const posts = await fetch('../search_index.json').then(r => r.json());
console.log(`共有 ${posts.length} 篇文章`);
```

## 引用

> 好的工具应该把复杂性藏起来，把简单留给使用它的人。
>
> —— OverCome 设计理念

## 表格

| 功能 | 是否内置 | 说明 |
| --- | :---: | --- |
| 全文搜索 | ✅ | 前端检索，无需后端 |
| RSS 订阅 | ✅ | Atom 格式 |
| 评论系统 | ❌ | 可自行集成 Giscus |
| 多作者 | ❌ | 单作者为主 |

## 分割线与图片

---

以上即本站 Markdown 渲染能力的完整演示，更多写法可参考 [GitHub 官方 Markdown 指南](https://docs.github.com/zh/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax)。