# -*- coding: utf-8 -*-
"""
OverCome - 零依赖静态博客生成器
运行: python3 build.py   (输出到 dist/)

仅使用 Python 标准库, 无任何第三方依赖。
"""
import json
import os
import re
import shutil
import html
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
THEME = ROOT / "theme"
DIST = ROOT / "dist"

# ---------------------------------------------------------------- 配置 ----

def load_config():
    cfg_path = ROOT / "config.json"
    with open(cfg_path, encoding="utf-8") as fp:
        cfg = json.load(fp)
    site = cfg["site"]
    site.setdefault("subtitle", "")
    site.setdefault("base", "")
    site.setdefault("timezone", "Asia/Shanghai")
    site.setdefault("date_format", "%Y-%m-%d")
    site.setdefault("posts_per_page", 6)
    site.setdefault("author", site.get("author", ""))
    site.setdefault("email", "")
    site.setdefault("since", datetime.date.today().year)
    site.setdefault("description", "")
    cfg["site"] = site
    return cfg


CONFIG = load_config()
SITE = CONFIG["site"]

# 构建期全局文章列表 (供 Renderer 右侧栏组件使用, build() 中填充)
_ALL_POSTS = []


def assets_version():
    """静态资源版本号: 优先用 CI 中的提交 SHA, 否则本地 git 短 SHA, 兜底时间戳。
    附加到 css/js 链接的 ?v= 参数, 避免 CDN 缓存导致旧资源滞留在边缘节点。"""
    sha = os.environ.get("GITHUB_SHA", "")
    if sha:
        return sha[:8]
    try:
        short = os.popen("git -C %s rev-parse --short HEAD" % ROOT).read().strip()
        if short:
            return short
    except Exception:
        pass
    return datetime.datetime.now().strftime("%Y%m%d%H%M")



# ----------------------------------------------------------- 工具函数 ----

def esc(text):
    return html.escape(str(text), quote=False)


def slugify(text):
    text = str(text).lower().strip()
    text = re.sub(r"[\s_，,、/]+", "-", text)
    text = re.sub(r"[^\w\u4e00-\u9fff-]", "", text, flags=re.UNICODE)
    return text.strip("-")


def parse_front_matter(text):
    """解析 --- 包裹的 front matter (支持 key: value / key: [a, b])"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    data = {}
    body = text
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
            else:
                value = re.sub(r"^['\"]|['\"]$", "", value)
            data[key] = value
    return data, body.strip()


def parse_date(s, now=None):
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def date_fmt(d, fmt=None):
    if not d:
        return ""
    return d.strftime(fmt or SITE.get("date_format", "%Y-%m-%d"))


# ----------------------------------------------------- 轻量 Markdown 解析 ----

class Markdown:
    """支持常用语法的轻量 Markdown 解析器"""

    def __init__(self):
        self.headings = []          # [(level, id, text)]
        self._anchor_counter = {}
        self._out = []

    # --- 行内解析 ---
    def inline(self, text):
        if "`" in text:
            text = re.sub(r"`([^`]+)`", lambda m: '<code class="inline">%s</code>' % esc(m.group(1)), text)

        def repl_link(m):
            before, alt, url, title, after = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            if before and before.endswith("!"):
                return before[:-1] + f'<img src="{esc(url)}" alt="{esc(alt)}" loading="lazy">' + (f'<span class="img-cap">{esc(title)}</span>' if title else "")
            cap = self.inline(alt)
            t = f' title="{esc(title)}"' if title else ""
            return f'<a href="{esc(url)}" target="_blank" rel="noopener nofollow"{t}>{cap}</a>' + after

        text = re.sub(
            r"(!?)\[([^\]]+)\]\(([^)\s]+)(?:\s+[\"']([^\"']+)[\"'])?\)(.*)",
            repl_link, text, flags=re.S)

        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
        text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"(?<![\w_])_([^_\n]+)_(?![\w_])", r"<em>\1</em>", text)
        return text

    def _anchor(self, text):
        base = slugify(re.sub(r"<[^>]+>", "", text))
        if not base:
            base = "sec"
        n = self._anchor_counter.get(base, 0)
        self._anchor_counter[base] = n + 1
        return base if n == 0 else f"{base}-{n}"

    # --- 块级 ---
    def block(self, text):
        lines = text.split("\n")
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 代码块
            m = re.match(r"```(\w*)", stripped)
            if m:
                lang = m.group(1)
                buf = []
                i += 1
                while i < n and not lines[i].strip().startswith("```"):
                    buf.append(lines[i])
                    i += 1
                i += 1
                code = "\n".join(buf)
                if lang:
                    self._out.append(f'<pre class="code-block"><code class="lang-{esc(lang)}">{esc(code)}</code></pre>')
                else:
                    self._out.append(f'<pre class="code-block"><code>{esc(code)}</code></pre>')
                self._out.append('<button class="code-copy" type="button" title="复制代码">复制</button>')
                continue

            # 标题
            m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", stripped)
            if m:
                level = len(m.group(1))
                raw = m.group(2)
                aid = self._anchor(raw)
                self.headings.append((level, aid, self.inline(raw)))
                self._out.append(f'<h{level} id="{aid}">{self.inline(raw)}</h{level}>')
                i += 1
                continue

            # 分割线
            if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
                self._out.append("<hr>")
                i += 1
                continue

            # 表格
            if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?[\s:|-]*$", lines[i + 1]) and "-" in lines[i + 1]:
                head = [c.strip() for c in line.strip().strip("|").split("|")]
                i += 2
                rows = []
                while i < n and "|" in lines[i] and lines[i].strip():
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                    i += 1
                thead = "".join(f"<th>{esc(h)}</th>" for h in head)
                tbody = ""
                for row in rows:
                    tds = "".join(f"<td>{self.inline(c)}</td>" for c in row)
                    tbody += f"<tr>{tds}</tr>"
                self._out.append(
                    f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>'
                )
                continue

            # 引用
            if stripped.startswith(">"):
                buf = []
                while i < n and lines[i].strip().startswith(">"):
                    buf.append(re.sub(r"^>\s?", "", lines[i]))
                    i += 1
                sub = Markdown()
                sub.block("\n".join(buf))
                self._out.append(f'<blockquote>{"".join(sub._out)}</blockquote>')
                continue

            # 列表 (无序/有序/任务)
            if re.match(r"^\s*[-*+]\s+", stripped):
                buf = []
                while i < n and re.match(r"^\s*[-*+]\s+", lines[i]):
                    content = re.sub(r"^\s*[-*+]\s+", "", lines[i])
                    task = re.match(r"^\[([ xX])\]\s+(.*)", content)
                    if task:
                        checked = " checked" if task.group(1).lower() == "x" else ""
                        buf.append(f'<li class="task"><input type="checkbox" disabled{checked}><span>{self.inline(task.group(2))}</span></li>')
                    else:
                        buf.append(f"<li>{self.inline(content)}</li>")
                    i += 1
                self._out.append("<ul>" + "".join(buf) + "</ul>")
                continue

            if re.match(r"^\s*\d+[.)]\s+", stripped):
                buf = []
                while i < n and re.match(r"^\s*\d+[.)]\s+", lines[i]):
                    content = re.sub(r"^\s*\d+[.)]\s+", "", lines[i])
                    buf.append(f"<li>{self.inline(content)}</li>")
                    i += 1
                self._out.append("<ol>" + "".join(buf) + "</ol>")
                continue

            # 空行
            if not stripped:
                i += 1
                continue

            # 段落 (收集连续非空行)
            buf = [line]
            i += 1
            while i < n and lines[i].strip() and not re.match(r"^(#{1,6}\s|```|>\s|[-*+]\s|\d+[.)]\s|\s*\|)", lines[i].strip()):
                buf.append(lines[i])
                i += 1
            para = " ".join(x.strip() for x in buf if x.strip())
            self._out.append(f"<p>{self.inline(para)}</p>")

        return "".join(self._out)

    def render(self, text):
        self.__init__()
        return self.block(text)


def md_to_html(text):
    return Markdown().render(text)


# ------------------------------------------------------------ 读取内容 ----

def load_posts():
    posts = []
    for fp in sorted((CONTENT / "posts").glob("*.md"), reverse=True):
        raw = fp.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw)
        if str(meta.get("draft", "")).lower() in ("true", "1", "yes"):
            continue
        date = parse_date(meta.get("date")) or parse_date(fp.name[:10])
        if not date:
            date = datetime.date.fromtimestamp(fp.stat().st_mtime)
        stem = fp.stem
        stem = re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", stem)
        slug = meta.get("slug") or stem
        title = meta.get("title") or slug
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        category = meta.get("category") or meta.get("categories") or "未分类"
        summary = meta.get("summary") or ""
        cover = meta.get("cover") or ""
        pinned = str(meta.get("pinned", "")).lower() in ("true", "1", "yes", "置顶")
        featured = str(meta.get("featured", "")).lower() in ("true", "1", "yes", "封面")
        content_html = md_to_html(body)
        word_count = len(re.sub(r"\s", "", body))
        reading_min = max(1, round(word_count / 420))
        tmp = Markdown()
        tmp.render(body)
        posts.append({
            "slug": slug,
            "title": title,
            "date": date,
            "date_str": date_fmt(date),
            "tags": tags,
            "category": category,
            "summary": summary,
            "cover": cover,
            "pinned": pinned,
            "featured": featured,
            "url": f"posts/{slug}/",
            "content_html": content_html,
            "content_text": re.sub(r"<[^>]+>", "", content_html),
            "word_count": word_count,
            "reading_min": reading_min,
            "headings": tmp.headings,
            "status": "published",
        })
    # 置顶优先(True>False), 同组内按日期倒序
    posts.sort(key=lambda p: (p["pinned"], p["date"]), reverse=True)
    return posts


def load_pages():
    """独立页面: content/pages/*.md 走 Markdown; *.html 或 front matter raw=true 时原样透传(自定义 HTML)"""
    pages = []
    for fp in sorted((CONTENT / "pages").iterdir()):
        if fp.suffix not in (".md", ".html"):
            continue
        raw = fp.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw)
        slug = meta.get("slug") or fp.stem
        title = meta.get("title") or slug
        is_raw = fp.suffix == ".html" or str(meta.get("raw", "")).lower() in ("true", "1", "yes")
        content_html = body if is_raw else md_to_html(body)
        pages.append({
            "slug": slug,
            "title": title,
            "url": f"{slug}/" if slug != "index" else "",
            "content_html": content_html,
            "content_text": re.sub(r"<[^>]+>", "", content_html),
        })
    return pages


def load_docs():
    """文档: content/docs/*.md, 支持 category 归类, 生成 /docs/ 目录页与 /docs/<slug>/ 详情页"""
    docs = []
    for fp in sorted((CONTENT / "docs").glob("*.md")):
        raw = fp.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw)
        if str(meta.get("draft", "")).lower() in ("true", "1", "yes"):
            continue
        date = parse_date(meta.get("date")) or datetime.date.fromtimestamp(fp.stat().st_mtime)
        slug = meta.get("slug") or fp.stem
        title = meta.get("title") or slug
        category = meta.get("category") or "使用指南"
        summary = meta.get("summary") or ""
        tmp = Markdown()
        content_html = tmp.render(body)
        docs.append({
            "slug": slug,
            "title": title,
            "date": date,
            "date_str": date_fmt(date),
            "category": category,
            "summary": summary,
            "url": f"docs/{slug}/",
            "content_html": content_html,
            "content_text": re.sub(r"<[^>]+>", "", content_html),
            "headings": tmp.headings,
        })
    docs.sort(key=lambda d: d["date"], reverse=True)
    return docs


def compute_indexes(posts):
    categories = {}
    tags = {}
    archive = {}
    for p in posts:
        categories.setdefault(p["category"], []).append(p)
        for t in p["tags"]:
            tags.setdefault(t, []).append(p)
        key = p["date"].strftime("%Y年%m月")
        archive.setdefault(key, []).append(p)
    for v in categories.values():
        v.sort(key=lambda p: p["date"], reverse=True)
    for v in tags.values():
        v.sort(key=lambda p: p["date"], reverse=True)
    return categories, tags, archive


def related_posts(post, posts, k=3):
    scored = []
    for p in posts:
        if p["slug"] == post["slug"]:
            continue
        score = len(set(p["tags"]) & set(post["tags"])) * 2
        if p["category"] == post["category"]:
            score += 3
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (x[0], x[1]["date"]), reverse=True)
    return [p for _, p in scored[:k]]


# -------------------------------------------------------------- 渲染 ----

class Renderer:
    """root 前缀: 空 = 根目录页面; '../' = 一级子目录; '../../' = 二级子目录"""

    def __init__(self):
        self.base = (THEME / "templates" / "base.html").read_text(encoding="utf-8")
        self.nav = CONFIG.get("nav", [])
        self.social = CONFIG.get("social", {})
        self.dist = DIST

    def page(self, title, body, *, root, active="", description="", extra_head="", side_toc="", show_right=True):
        nav_html = []
        for item in self.nav:
            url = item.get("url", "")
            cls = ' class="active"' if (item.get("key") or url) == active else ""
            nav_html.append(f'<a href="{root}{url}"{cls}>{esc(item.get("label", ""))}</a>')
        social_html = ""
        if self.social:
            icons = ""
            for key, val in self.social.items():
                if not val:
                    continue
                href = val
                if not href.startswith(("http://", "https://", "mailto:")):
                    href = root + href
                icons += f'<a class="social-link" href="{esc(href)}" target="_blank" rel="noopener nofollow" aria-label="{esc(key)}">{esc(key)}</a>'
            if icons:
                social_html = f'<div class="social">{icons}</div>'
        right_html = self.right_bar_html(root) if show_right else ""
        return self.base.replace("{{title}}", esc(title)) \
            .replace("{{site_title}}", esc(SITE["title"])) \
            .replace("{{subtitle}}", esc(SITE.get("subtitle", ""))) \
            .replace("{{description}}", esc(description or SITE.get("description", ""))) \
            .replace("{{root}}", root) \
            .replace("{{nav}}", "".join(nav_html)) \
            .replace("{{social}}", social_html) \
            .replace("{{side_toc}}", side_toc) \
            .replace("{{right_bar}}", right_html) \
            .replace("{{site_year}}", str(datetime.date.today().year)) \
            .replace("{{site_author}}", esc(SITE.get("author", ""))) \
            .replace("{{extra_head}}", extra_head) \
            .replace("{{analytics}}", analytics_html()) \
            .replace("{{assets_version}}", assets_version()) \
            .replace("{{content}}", body)

    def right_bar_html(self, root):
        """右侧栏组件 (最新文章 / 标签云 / 归档 / 简介), 由 config.sidebar_right 控制, 可整体开关"""
        cfg = CONFIG.get("sidebar_right") or {}
        if not cfg.get("enabled"):
            return ""
        widgets = []
        # 最新文章
        if cfg.get("show_latest", True):
            n = int(cfg.get("latest_count", 5))
            lst = [p for p in _ALL_POSTS if not p.get("pinned")][:n] or _ALL_POSTS[:n]
            items = "".join(
                f'<li><a href="{root}{p["url"]}">{esc(p["title"])}</a><span class="w-date">{p["date_str"]}</span></li>'
                for p in lst)
            if lst:
                widgets.append(f'<div class="widget"><h3>最新文章</h3><ul class="widget-list">{items}</ul></div>')
        # 标签云
        if cfg.get("show_tags", True):
            _, tags, _ = compute_indexes(_ALL_POSTS)
            top = sorted(tags.items(), key=lambda kv: -len(kv[1]))[:cfg.get("tags_count", 16)]
            chips = "".join(
                f'<a class="chip chip-tag" href="{root}tags/{slugify(t)}/">{esc(t)}<em>{len(ps)}</em></a>'
                for t, ps in top)
            if chips:
                widgets.append(f'<div class="widget"><h3>标签</h3><div class="widget-tags">{chips}</div></div>')
        # 归档
        if cfg.get("show_archive", True):
            widgets.append(
                f'<div class="widget"><h3>归档</h3><ul class="widget-list"><li><a href="{root}archive/">全部文章 ({len(_ALL_POSTS)})</a><span class="w-date">{SITE["since"]} 至今</span></li></ul></div>')
        if not widgets:
            return ""
        return '<aside class="right-bar" aria-label="侧边栏">' + "".join(widgets) + "</aside>"


def analytics_html():
    """站点统计脚本注入 (不蒜子 / 自定义脚本), 默认关闭"""
    cfg = CONFIG.get("analytics") or {}
    if not cfg.get("enabled"):
        return ""
    provider = cfg.get("provider", "")
    script = cfg.get("script", "")
    if provider == "busuanzi":
        return '''<div class="site-stats" aria-label="站点统计">
  <span>已运行 <span id="busuanzi_value_site_uv"></span> 天</span>
  <span>· 访问 <span id="busuanzi_value_site_pv"></span></span>
</div>
<script async src="https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js"></script>'''
    if script:
        return f'''<div class="site-stats site-stats-custom"></div>
<script async src="{esc(script)}"></script>'''
    return ""


def comments_html():
    """Giscus 评论区块。在 giscus.app 为仓库生成配置后回填 repoId/categoryId 并设 enabled=true 即启用"""
    cfg = CONFIG.get("comments") or {}
    if not cfg.get("enabled"):
        return ""
    repo = cfg.get("repo", "")
    repo_id = cfg.get("repoId", "")
    category = cfg.get("category", "")
    category_id = cfg.get("categoryId", "")
    if not (repo and repo_id and category and category_id):
        return ""
    return f'''
<section class="comments" id="comments">
  <h3 class="comments-title">评论</h3>
  <script src="https://giscus.app/client.js"
    data-repo="{esc(repo)}"
    data-repo-id="{esc(repo_id)}"
    data-category="{esc(category)}"
    data-category-id="{esc(category_id)}"
    data-mapping="pathname"
    data-strict="0"
    data-reactions-enabled="1"
    data-emit-metadata="0"
    data-input-position="top"
    data-theme="preferred_color_scheme"
    data-lang="zh-CN"
    data-loading="lazy"
    crossorigin="anonymous" async>
  </script>
</section>'''


def render_index(posts, page_no=1, per_page=6):
    r = Renderer()
    total = len(posts)
    pages = max(1, (total + per_page - 1) // per_page)
    page_no = max(1, min(page_no, pages))
    start = (page_no - 1) * per_page
    chunk = posts[start:start + per_page]

    root = "" if page_no == 1 else "../../"
    cards = []
    for p in chunk:
        pin_badge = '<span class="pin-badge" title="置顶文章">置顶</span>' if p.get("pinned") else ""
        tags_html = "".join(
            f'<a class="chip chip-tag" href="{root}tags/{slugify(t)}/">{esc(t)}</a>'
            for t in p["tags"][:4])
        cover_html = ""
        if p.get("cover"):
            cover_html = f'<div class="card-cover"><img src="{esc(p["cover"])}" alt="" loading="lazy"></div>'
        else:
            cover_html = '<div class="card-cover card-cover-placeholder"><span></span></div>'
        cards.append(f'''
<article class="card">
  {cover_html}
  <div class="card-body">
    <div class="card-meta">
      <span class="date">{p["date_str"]}</span>
      <a class="chip chip-cat" href="{root}categories/{slugify(p["category"])}/">{esc(p["category"])}</a>
      <span class="read-min">{p["reading_min"]} 分钟阅读 · {p["word_count"]} 字</span>
    </div>
    <h2 class="card-title">{pin_badge}<a href="{root}{p["url"]}">{esc(p["title"])}</a></h2>
    <p class="card-summary">{esc(p["summary"] or p["content_text"][:120])}</p>
    <div class="card-tags">{tags_html}</div>
  </div>
</article>''')

    pagination = ""
    if pages > 1:
        items = []
        if page_no > 1:
            prev_url = root + ("index.html" if page_no == 2 else f"page/{page_no - 1}/")
            items.append(f'<a class="pager prev" href="{prev_url}">‹ 上一页</a>')
        items.append(f'<span class="pager-info">{page_no} / {pages} · 共 {total} 篇</span>')
        if page_no < pages:
            items.append(f'<a class="pager next" href="{root}page/{page_no + 1}/">下一页 ›</a>')
        pagination = f'<nav class="pagination">{"".join(items)}</nav>'

    hero = ""
    if page_no == 1:
        hero_cfg = CONFIG.get("hero") or {}
        if hero_cfg.get("enabled", True):
            h_title = hero_cfg.get("title") or SITE.get("title", "")
            h_desc = hero_cfg.get("description") or SITE.get("description", "")
            hero = f'''
<section class="hero">
  <h1>{esc(h_title)}</h1>
  <p class="hero-sub">{esc(h_desc)}</p>
</section>'''

    # 封面文章区: 首页首屏展示 featured 标记的文章 (封面图大卡)
    featured_cards = ""
    if page_no == 1:
        feats = [p for p in posts if p.get("featured")][:3]
        if feats:
            feats_html = []
            for p in feats:
                if p.get("cover"):
                    fcov = f'<img src="{esc(p["cover"])}" alt="" loading="lazy">'
                else:
                    fcov = '<span class="featured-cover-placeholder"></span>'
                feats_html.append(f'''
<a class="featured-card" href="{root}{p["url"]}">
  <div class="featured-cover">{fcov}<span class="featured-badge">封面文章</span></div>
  <div class="featured-info">
    <span class="date">{p["date_str"]}</span>
    <h2>{esc(p["title"])}</h2>
    <p>{esc(p["summary"] or p["content_text"][:80])}</p>
  </div>
</a>''')
            featured_cards = '<section class="featured-row">' + "".join(feats_html) + "</section>"

    body = hero + featured_cards + '<div class="cards">' + "".join(cards) + "</div>" + pagination
    return r.page(SITE.get("title", ""), body, root=root, active="index",
                  description=SITE.get("description", ""))


def render_post(post, posts):
    r = Renderer()
    root = "../../"
    prev = next_p = None
    for idx, p in enumerate(posts):
        if p["slug"] == post["slug"]:
            prev = posts[idx + 1] if idx + 1 < len(posts) else None   # 更早的
            next_p = posts[idx - 1] if idx > 0 else None              # 更新的
            break

    side_toc = ""
    if post["headings"]:
        items = []
        for lv, aid, text in post["headings"]:
            cls = "toc-h3" if lv >= 3 else ""
            items.append(f'<a class="{cls}" href="#{aid}">{text}</a>')
        side_toc = '<nav class="side-toc"><div class="side-toc-title">文章目录</div><div class="side-toc-links">' + "".join(items) + "</div></nav>"

    tags_html = "".join(
        f'<a class="chip chip-tag" href="{root}tags/{slugify(t)}/">{esc(t)}</a>'
        for t in post["tags"])

    prev_html = f'<a class="nav-item prev" href="{root}posts/{prev["slug"]}/"><span>← 更早</span><b>{esc(prev["title"])}</b></a>' if prev else "<span></span>"
    next_html = f'<a class="nav-item next" href="{root}posts/{next_p["slug"]}/"><span>更新 →</span><b>{esc(next_p["title"])}</b></a>' if next_p else "<span></span>"

    rel = related_posts(post, posts)
    rel_html = ""
    if rel:
        items = "".join(
            f'<li><a href="{root}posts/{p["slug"]}/">{esc(p["title"])}</a><span>{p["date_str"]}</span></li>'
            for p in rel)
        rel_html = f'<section class="related"><h3>相关阅读</h3><ul>{items}</ul></section>'

    article = f'''
<article class="post">
  <header class="post-header">
    <div class="post-meta">
      <span class="date">{post["date_str"]}</span>
      <a class="chip chip-cat" href="{root}categories/{slugify(post["category"])}/">{esc(post["category"])}</a>
      <span class="read-min">{post["reading_min"]} 分钟 · {post["word_count"]} 字</span>
    </div>
    <h1 class="post-title">{esc(post["title"])}</h1>
    <div class="post-tags">{tags_html}</div>
  </header>
  <div class="post-layout">
    <div class="post-body">{post["content_html"]}</div>
  </div>
  <footer class="post-footer">
    <nav class="post-nav">{prev_html}{next_html}</nav>
  </footer>
  {rel_html}
</article>''' + comments_html()
    return r.page(post["title"], article, root=root, active="",
                  description=post.get("summary", ""), side_toc=side_toc,
                  extra_head=f'<link rel="stylesheet" href="../../static/css/highlight.css?v={assets_version()}">')


def render_page(page):
    r = Renderer()
    body = f'<article class="page post"><header class="post-header"><h1 class="page-title">{esc(page["title"])}</h1></header><div class="post-body">{page["content_html"]}</div></article>'
    return r.page(page["title"], body, root="../", active="page", description=SITE.get("description", ""))


def render_archive(posts):
    r = Renderer()
    _, _, archive = compute_indexes(posts)
    html_parts = []
    for key in sorted(archive.keys(), reverse=True):
        items = "".join(
            f'<li><span class="date">{p["date_str"]}</span><a href="../posts/{p["slug"]}/">{esc(p["title"])}</a><span class="cat">{esc(p["category"])}</span></li>'
            for p in archive[key])
        html_parts.append(f'<section class="archive-group"><h2>{esc(key)} <em>{len(archive[key])}</em></h2><ul>{items}</ul></section>')
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">归档</h1><p class="page-sub">共 {len(posts)} 篇文章</p></header><div class="archive">{"".join(html_parts)}</div></div>'
    return r.page("归档", body, root="../", active="archive")


def render_tags(posts):
    r = Renderer()
    _, tags, _ = compute_indexes(posts)
    items = []
    for tag, ps in sorted(tags.items(), key=lambda kv: -len(kv[1])):
        size = 1 + min(2, len(ps) // 3)
        items.append(f'<a class="tag-cloud tag-{size}" href="../tags/{slugify(tag)}/">{esc(tag)}<em>{len(ps)}</em></a>')
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">标签</h1></header><div class="tag-cloud-wrap">{"".join(items)}</div></div>'
    return r.page("标签", body, root="../", active="tags")


def render_tag(tag, posts):
    r = Renderer()
    root = "../../"
    items = "".join(
        f'<li><span class="date">{p["date_str"]}</span><a href="{root}posts/{p["slug"]}/">{esc(p["title"])}</a></li>'
        for p in posts)
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">#{esc(tag)}</h1><p class="page-sub">{len(posts)} 篇文章</p></header><ul class="flat-list">{items}</ul></div>'
    return r.page(f"标签: {tag}", body, root=root, active="tags")


def render_category(cat, posts):
    r = Renderer()
    root = "../../"
    items = "".join(
        f'<li><span class="date">{p["date_str"]}</span><a href="{root}posts/{p["slug"]}/">{esc(p["title"])}</a></li>'
        for p in posts)
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">{esc(cat)}</h1><p class="page-sub">{len(posts)} 篇文章</p></header><ul class="flat-list">{items}</ul></div>'
    return r.page(f"分类: {cat}", body, root=root, active="")


def render_search():
    r = Renderer()
    body = f'''<div class="page post"><header class="post-header"><h1 class="page-title">搜索</h1></header>
<div class="search-box"><input id="search-input" type="search" placeholder="输入关键词，如：Markdown、部署…" autocomplete="off"><button id="search-btn" type="button">搜索</button></div>
<div id="search-hint" class="search-hint">输入关键词即可全文检索本站内容</div>
<ul id="search-results" class="search-results"></ul></div>
<script src="../static/js/search.js?v={assets_version()}" defer></script>'''
    return r.page("搜索", body, root="../", active="search", show_right=False)


def render_404():
    r = Renderer()
    body = '<div class="page post notfound"><h1 class="page-title">404</h1><p class="hero-sub">页面不存在或已被移动。</p><a class="btn" href="index.html">返回首页</a></div>'
    return r.page("页面未找到", body, root="", active="", show_right=False)


# ----------------------------------------------------- 文档 / 友链 / 问卷 / 短链 ----

def render_docs_index(docs):
    """文档目录页 /docs/: 按分类分组展示"""
    r = Renderer()
    groups = {}
    for d in docs:
        groups.setdefault(d["category"], []).append(d)
    blocks = []
    for cat in sorted(groups):
        items = "".join(
            f'<li><span class="date">{d["date_str"]}</span><a href="../{d["url"]}">{esc(d["title"])}</a><span class="cat">{esc(d.get("summary") or d["category"])}</span></li>'
            for d in groups[cat])
        blocks.append(f'<section class="archive-group"><h2>{esc(cat)} <em>{len(groups[cat])}</em></h2><ul>{items}</ul></section>')
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">文档</h1><p class="page-sub">共 {len(docs)} 篇文档</p></header><div class="archive">{"".join(blocks)}</div></div>'
    return r.page("文档", body, root="../", active="docs")


def render_doc(doc, docs):
    """文档详情页 /docs/<slug>/: 含目录与文档内前后篇"""
    r = Renderer()
    root = "../../"
    side_toc = ""
    if doc["headings"]:
        items = []
        for lv, aid, text in doc["headings"]:
            cls = "toc-h3" if lv >= 3 else ""
            items.append(f'<a class="{cls}" href="#{aid}">{text}</a>')
        side_toc = '<nav class="side-toc"><div class="side-toc-title">文档目录</div><div class="side-toc-links">' + "".join(items) + "</div></nav>"
    prev = next_d = None
    for idx, d in enumerate(docs):
        if d["slug"] == doc["slug"]:
            prev = docs[idx + 1] if idx + 1 < len(docs) else None
            next_d = docs[idx - 1] if idx > 0 else None
            break
    prev_html = f'<a class="nav-item prev" href="{root}{prev["url"]}"><span>← 上一篇</span><b>{esc(prev["title"])}</b></a>' if prev else "<span></span>"
    next_html = f'<a class="nav-item next" href="{root}{next_d["url"]}"><span>下一篇 →</span><b>{esc(next_d["title"])}</b></a>' if next_d else "<span></span>"
    article = f'''
<article class="post">
  <header class="post-header">
    <div class="post-meta">
      <span class="date">{doc["date_str"]}</span>
      <span class="chip chip-cat">{esc(doc["category"])}</span>
      <a class="crumb" href="../../docs/">← 返回文档目录</a>
    </div>
    <h1 class="post-title">{esc(doc["title"])}</h1>
  </header>
  <div class="post-layout">
    <div class="post-body">{doc["content_html"]}</div>
  </div>
  <footer class="post-footer"><nav class="post-nav">{prev_html}{next_html}</nav></footer>
</article>'''
    return r.page(doc["title"], article, root=root, active="docs",
                  description=doc.get("summary", ""), side_toc=side_toc)


def render_links(friends, submit_url=""):
    """友链页 /links/: 展示友链 + 站内自助提交表单 (提交后组装 GitHub Issue 预填请求)"""
    r = Renderer()
    root = "../"
    if not friends:
        items = '<li class="empty">暂无友链，欢迎申请加入。</li>'
    else:
        cards = []
        for f in friends:
            avatar = f.get("avatar") or ""
            img = f'<img src="{esc(avatar)}" alt="" loading="lazy">' if avatar else f'<span class="avatar-ph">{esc((f.get("name") or "友")[0])}</span>'
            cards.append(f'''
<li class="friend-card">
  <div class="friend-avatar">{img}</div>
  <div class="friend-meta">
    <a href="{esc(f.get("url", "#"))}" target="_blank" rel="noopener nofollow"><b>{esc(f.get("name", ""))}</b></a>
    <p>{esc(f.get("desc", ""))}</p>
  </div>
</li>''')
        items = "".join(cards)
    repo = CONFIG.get("link_repo", "")
    # 站内自助提交表单: 无后端, 提交时把字段组装成 GitHub Issue 预填链接打开
    form_html = f'''<section class="link-submit">
  <h3 class="widget-h">自助申请友链</h3>
  <p class="link-submit-tip">填写以下信息提交申请，站长审核通过后会加入友链列表。请确保站点可正常访问、内容与本站互相尊重。</p>
  <form id="friend-form" class="survey" novalidate>
    <div class="survey-fields">
      <label class="form-field"><span>网站名称 *</span><input type="text" name="name" required placeholder="你的站点名称"></label>
      <label class="form-field"><span>网站地址 *</span><input type="url" name="url" required placeholder="https://example.com"></label>
      <label class="form-field"><span>一句话简介</span><input type="text" name="desc" placeholder="站点定位或一句话介绍"></label>
      <label class="form-field"><span>头像地址(可选)</span><input type="url" name="avatar" placeholder="https://example.com/avatar.png"></label>
    </div>
    <div class="form-actions">
      <button class="btn" type="submit">提交申请</button>
      <span class="form-note">提交后打开 GitHub Issue 预填模板，确认发送即完成申请</span>
    </div>
  </form>
</section>
<script>
(function () {{
  var form = document.getElementById('friend-form');
  if (!form) return;
  form.addEventListener('submit', function (ev) {{
    ev.preventDefault();
    var d = new FormData(form);
    var name = d.get('name') || '', url = d.get('url') || '', desc = d.get('desc') || '', avatar = d.get('avatar') || '';
    var body = '站点名称：' + name + '\\n站点地址：' + url + '\\n简介：' + desc + '\\n头像：' + avatar;
    var issue = 'https://github.com/{esc(repo)}/issues/new?title=' + encodeURIComponent('申请友链：' + name) + '&body=' + encodeURIComponent(body);
    window.open(issue, '_blank', 'noopener');
  }});
}})();
</script>'''
    submit_block = ""
    if submit_url:
        submit_block = f'<div class="link-submit"><p>想交换友链？<a class="btn" href="{esc(submit_url)}" target="_blank" rel="noopener nofollow">申请加入</a></p></div>'
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">友情链接</h1><p class="page-sub">共 {len(friends)} 位伙伴</p></header><ul class="friend-list">{items}</ul>{submit_block}{form_html}</div>'
    return r.page("友情链接", body, root=root, active="links")


def render_survey(form):
    """问卷/单表页 /forms/<slug>/: 无后端架构, 配置 endpoint 则 AJAX 提交, 否则 mailto 聚合"""
    r = Renderer()
    root = "../../"
    slug = form.get("slug", "form")
    title = form.get("title", "问卷")
    endpoint = form.get("endpoint", "")
    fields_html = []
    for f in form.get("fields", []):
        fname = esc(f.get("name", ""))
        flabel = esc(f.get("label", f.get("name", "")))
        req = " required" if f.get("required") else ""
        ph = f' placeholder="{esc(f.get("placeholder", ""))}"' if f.get("placeholder") else ""
        ftype = f.get("type", "text")
        if ftype == "textarea":
            fields_html.append(f'<label class="form-field"><span>{flabel}</span><textarea name="{fname}"{req}{ph} rows="4"></textarea></label>')
        elif ftype == "select":
            opts = "".join(f'<option value="{esc(o)}">{esc(o)}</option>' for o in f.get("options", []))
            fields_html.append(f'<label class="form-field"><span>{flabel}</span><select name="{fname}"{req}>{opts}</select></label>')
        else:
            fields_html.append(f'<label class="form-field"><span>{flabel}</span><input type="{esc(ftype)}" name="{fname}"{req}{ph}></label>')
    note = esc(form.get("note", ""))
    # 提交逻辑: 配置了 endpoint 的走 fetch (如 Formspree/表单服务), 否则组装 mailto(无后端)
    js = '''<script>
(function () {
  var form = document.getElementById('survey-form');
  if (!form) return;
  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var parts = [];
    new FormData(form).forEach(function (v, k) { parts.push(k + ': ' + v); });
    var ep = form.getAttribute('data-endpoint');
    if (ep) {
      fetch(ep, { method: 'POST', body: new FormData(form) })
        .then(function () { alert('提交成功，感谢反馈！'); form.reset(); })
        .catch(function () { sendMail(parts); });
    } else { sendMail(parts); }
  });
  function sendMail(parts) {
    var subject = encodeURIComponent('{subject}');
    var bodyTxt = encodeURIComponent(parts.join('\\n'));
    window.location.href = 'mailto:{mailto}?subject=' + subject + '&body=' + bodyTxt;
  }
})();
</script>'''.replace("{subject}", title).replace("{mailto}", SITE.get("email", ""))
    body = f'''<div class="page post"><header class="post-header"><h1 class="page-title">{esc(title)}</h1></header>
<form class="survey" id="survey-form" data-endpoint="{esc(endpoint)}" novalidate>
  <div class="survey-fields">{''.join(fields_html)}</div>
  <div class="form-actions"><button class="btn" type="submit">提交</button><span class="form-note">{note}</span></div>
</form></div>{js}'''
    return r.page(title, body, root=root, active="", description=note)


def render_shortlink(key, target):
    """短链接落地页 /go/<key>/: meta refresh + JS 双重跳转, 无 JS 时提供手动链接"""
    t = esc(target)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={t}">
<script>location.replace({json.dumps(target)});</script>
<title>跳转中 · {esc(SITE.get("title", ""))}</title>
</head>
<body>
<p style="font-family:sans-serif;text-align:center;padding:3em 1em">正在跳转到 <a href="{t}">{t}</a>，未自动跳转请点击。</p>
</body>
</html>'''


# --------------------------------------------------------------- Feed ----

def render_feed(posts):
    base = SITE.get("base", "").rstrip("/") + "/"
    pub = (posts[0]["date"].isoformat() if posts else datetime.date.today().isoformat()) + "T00:00:00+08:00"
    entries = []
    for p in posts[:20]:
        desc = esc(p.get("summary") or p["content_text"][:200])
        entries.append(f'''<entry>
  <title>{esc(p["title"])}</title>
  <link href="{base}{p["url"]}"/>
  <id>{base}{p["url"]}</id>
  <published>{p["date"].isoformat()}T00:00:00+08:00</published>
  <updated>{p["date"].isoformat()}T00:00:00+08:00</updated>
  <author><name>{esc(SITE.get("author", ""))}</name></author>
  <category term="{esc(p["category"])}"/>
  <summary>{desc}</summary>
</entry>''')
    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{esc(SITE["title"])}</title>
  <subtitle>{esc(SITE.get("description", ""))}</subtitle>
  <link href="{base}"/>
  <link href="{base}feed.xml" rel="self"/>
  <updated>{pub}</updated>
  <id>{base}</id>
  <author><name>{esc(SITE.get("author", ""))}</name></author>
{chr(10).join(entries)}
</feed>'''
    return xml


def render_sitemap(posts, pages, docs):
    base = SITE.get("base", "").rstrip("/") + "/"
    urls = [
        f"  <url><loc>{base}</loc></url>",
        f"  <url><loc>{base}archive/</loc></url>",
        f"  <url><loc>{base}tags/</loc></url>",
        f"  <url><loc>{base}search/</loc></url>",
    ]
    if docs:
        urls.append(f"  <url><loc>{base}docs/</loc></url>")
    for pg in pages:
        urls.append(f'  <url><loc>{base}{pg["url"]}</loc></url>')
    for d in docs:
        urls.append(f'  <url><loc>{base}{d["url"]}</loc></url>')
    for p in posts:
        urls.append(f'  <url><loc>{base}{p["url"]}</loc></url>')
    return '<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"


def render_search_index(posts, pages, docs=None):
    data = []
    for p in posts:
        data.append({
            "type": "post",
            "title": p["title"],
            "url": SITE.get("base", "").rstrip("/") + "/" + p["url"],
            "date": p["date_str"],
            "category": p["category"],
            "tags": p["tags"],
            "summary": p.get("summary") or p["content_text"][:160],
            "content": p["content_text"][:600],
        })
    for pg in pages:
        data.append({
            "type": "page",
            "title": pg["title"],
            "url": SITE.get("base", "").rstrip("/") + "/" + pg["url"],
            "date": "",
            "category": "",
            "tags": [],
            "summary": pg["content_text"][:160],
            "content": pg["content_text"][:400],
        })
    for d in docs or []:
        data.append({
            "type": "doc",
            "title": d["title"],
            "url": SITE.get("base", "").rstrip("/") + "/" + d["url"],
            "date": d["date_str"],
            "category": d["category"],
            "tags": [],
            "summary": d.get("summary") or d["content_text"][:160],
            "content": d["content_text"][:400],
        })
    return json.dumps(data, ensure_ascii=False, indent=1)


# --------------------------------------------------------------- 构建 ----

def write(path, content, root=DIST):
    fp = root / path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")


def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    posts = load_posts()
    pages = load_pages()
    docs = load_docs()
    friends = CONFIG.get("friends") or []
    links = CONFIG.get("links") or {}
    forms = CONFIG.get("forms") or []
    link_submit = CONFIG.get("link_submit", "")
    global _ALL_POSTS
    _ALL_POSTS = posts

    # 首页 + 分页
    per_page = int(SITE.get("posts_per_page", 6))
    total_pages = max(1, (len(posts) + per_page - 1) // per_page)
    for page_no in range(1, total_pages + 1):
        if page_no == 1:
            write("index.html", render_index(posts, page_no, per_page))
        else:
            write(f"page/{page_no}/index.html", render_index(posts, page_no, per_page))

    # 文章页
    for p in posts:
        write(f"posts/{p['slug']}/index.html", render_post(p, posts))

    # 独立页面 (含自定义 HTML 页面)
    for pg in pages:
        if pg["slug"] == "index":
            write("index.html", render_page(pg))
        else:
            write(f"{pg['slug']}/index.html", render_page(pg))

    # 文档
    write("docs/index.html", render_docs_index(docs))
    for d in docs:
        write(f"docs/{d['slug']}/index.html", render_doc(d, docs))

    # 友链
    write("links/index.html", render_links(friends, link_submit))

    # 问卷 / 表单
    for form in forms:
        write(f"forms/{form['slug']}/index.html", render_survey(form))

    # 短链接落地页
    for key, target in links.items():
        if key and isinstance(target, str) and target.startswith(("http://", "https://", "mailto:")):
            write(f"go/{key}/index.html", render_shortlink(key, target))

    # 归档 / 标签 / 分类
    write("archive/index.html", render_archive(posts))
    write("tags/index.html", render_tags(posts))
    _, tags, _ = compute_indexes(posts)
    for tag, ps in tags.items():
        write(f"tags/{slugify(tag)}/index.html", render_tag(tag, ps))
    categories, _, _ = compute_indexes(posts)
    for cat, ps in categories.items():
        write(f"categories/{slugify(cat)}/index.html", render_category(cat, ps))

    # 工具页
    write("search/index.html", render_search())
    write("404.html", render_404())

    # 数据与协议
    write("feed.xml", render_feed(posts))
    write("sitemap.xml", render_sitemap(posts, pages, docs))
    write("search_index.json", render_search_index(posts, pages, docs))
    write("robots.txt", "User-agent: *\nAllow: /\n")

    # 静态资源
    src_static = THEME / "static"
    if src_static.exists():
        shutil.copytree(src_static, DIST / "static")

    print(f"[OK] 共生成 {len(posts)} 篇文章, {len(pages)} 个页面, {len(docs)} 篇文档, {len(friends)} 个友链, {len(forms)} 个表单, {len(links)} 条短链, 分页 {total_pages} 页")
    print(f"[OK] 站点输出目录: {DIST}")


if __name__ == "__main__":
    build()