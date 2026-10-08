# -*- coding: utf-8 -*-
"""OverCome 示例插件: 每日一言

演示插件生态的两类钩子:
  1) widget(context) -> str      : 在右侧栏渲染组件 (页面 widgets 配置写 "plugin:daily-quote")
  2) process(html, context) -> str : 对每个页面做构建期后处理

插件在构建机器本地运行, 只安装/信任你自己编写的插件。
"""

QUOTES = [
    ("少而精，快而稳。", "科技酱"),
    ("好文章，是改出来的。", "佚名"),
    ("先完成，再完美。", "佚名"),
    ("博客是一块自留地。", "OverCome"),
    ("写下来，才能想清楚。", "科技酱"),
]

_SENTINEL = "__OVERCOME_QUOTE_APPEND__"


def widget(context):
    """返回右侧栏组件 HTML (build.py 会包一层 .widget)"""
    text, author = QUOTES[0]
    root = context.get("root", "")
    return (
        f'<h3>每日一言</h3>'
        f'<blockquote class="plugin-quote">{text}<cite>—— {author}</cite></blockquote>'
        f'<p class="monitor-note">由 daily-quote 插件渲染 · <a href="{root}plugins/">插件生态</a></p>'
    )


def process(html, context):
    """构建期后处理: 仅向文章/文档/笔记详情页追加一句引用 (插在署名之前, 保持署名置底)"""
    if context.get("page_type") not in ("post", "doc", "note"):
        return html
    if "<footer class=\"post-footer\">" not in html and "</article>" not in html:
        return html
    # 按标题稳定轮换语录
    try:
        import datetime
        q = QUOTES[hash(datetime.date.today().isoformat() + context.get("title", "")) % len(QUOTES)]
    except Exception:
        q = QUOTES[0]
    quote_html = (
        f'<blockquote class="plugin-tail-quote">“{q[0]}”<cite>—— {q[1]}</cite></blockquote>'
    )
    if "<footer class=\"post-footer\">" in html:
        return html.replace("<footer class=\"post-footer\">", quote_html + "<footer class=\"post-footer\">", 1)
    return html.replace("</article>", quote_html + "</article>", 1)