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
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
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
    site.setdefault("posts_per_page", 10)
    site.setdefault("author", site.get("author", ""))
    site.setdefault("email", "")
    site.setdefault("since", datetime.date.today().year)
    site.setdefault("description", "")
    cfg["site"] = site
    # 新增配置节默认值 (保持缺失时兼容)
    cfg.setdefault("layout", {"card_width": "", "card_cover_height": 150, "content_max_width": 780})
    cfg.setdefault("link_strategy", {"internal": "self", "external": "blank"})
    cfg.setdefault("dynamic", {"enabled": True, "include_posts": True, "include_friend_rss": True,
                               "notes_sync": True, "items": []})
    cfg.setdefault("notes", {"enabled": True, "per_page": 10})
    cfg.setdefault("plugins", {"enabled": True, "path": "plugins"})
    cfg.setdefault("custom_widgets", [])
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
                return before[:-1] + f'<img src="{esc(url)}" alt="{esc(alt)}" loading="lazy" decoding="async">' + (f'<span class="img-cap">{esc(title)}</span>' if title else "")
            cap = self.inline(alt)
            t = f' title="{esc(title)}"' if title else ""
            # 链接跳转策略在运行期由 viewer.js 统一处理 (config.link_strategy),
            # 构建期不再写死 target 与 rel, 避免策略失效。
            return f'<a href="{esc(url)}"{t}>{cap}</a>' + after

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

            # 代码块 (复制按钮内置于 <pre> 左上角, 与 .code-copy 定位配合)
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
                btn = '<button class="code-copy" type="button" title="复制代码">复制</button>'
                if lang:
                    self._out.append(f'<pre class="code-block"><code class="lang-{esc(lang)}">{esc(code)}</code>{btn}</pre>')
                else:
                    self._out.append(f'<pre class="code-block"><code>{esc(code)}</code>{btn}</pre>')
                continue

            # 链接卡片: 独立成行 @[标题](https://…)
            m = re.match(r"^@\[([^\]]+)\]\(([^)\s]+)\)\s*$", stripped)
            if m:
                self._out.append(self.link_card(m.group(1), m.group(2)))
                i += 1
                continue

            # 网页嵌入卡片: 独立成行 :::embed <url> [标题]
            m = re.match(r"^:::\s*embed\s+(\S+?)(?:\s+(.+?))?\s*$", stripped, re.I)
            if m:
                self._out.append(self.embed_card(m.group(2) or "", m.group(1)))
                i += 1
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

    def link_card(self, title, url):
        """链接卡片: @[标题](https://…), 独立成行时渲染为卡片。
        图标在运行期由 viewer.js 填充 favicon, 失败自动隐藏。"""
        url = url.strip()
        m = re.match(r"^https?://([^/]+)", url)
        domain = m.group(1) if m else url
        icon = (f'<img class="lc-icon" src="https://icons.duckduckgo.com/ip3/{esc(domain)}.ico" alt="" '
                f'loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.remove()">'
                if m else '<span class="lc-icon lc-icon-ph" aria-hidden="true">↗</span>')
        t = esc(title) or esc(domain)
        return (f'<a class="link-card" href="{esc(url)}" target="_blank" rel="noopener nofollow">'
                f'{icon}<span class="lc-body"><b class="lc-title">{t}</b>'
                f'<span class="lc-domain">{esc(domain)}</span></span>'
                f'<span class="lc-arrow" aria-hidden="true">↗</span></a>')

    def embed_card(self, title, url):
        """网页嵌入卡片: :::embed <url> [标题], 独立成行时渲染为可滚动的 iframe 卡片。
        不支持被嵌入的目标站点由 iframe 自身的 X-Frame-Options 决定, 提供"新窗口打开"兜底。"""
        url = url.strip()
        m = re.match(r"^https?://([^/]+)", url)
        domain = m.group(1) if m else url
        t = esc(title) or esc(domain)
        return (f'<div class="embed-card"><div class="embed-bar">'
                f'<span class="embed-title" title="{esc(url)}">{t}</span>'
                f'<a class="embed-open" href="{esc(url)}" target="_blank" rel="noopener nofollow">新窗口打开 ↗</a>'
                f'</div><div class="embed-frame">'
                f'<iframe src="{esc(url)}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" '
                f'title="{t}"></iframe></div></div>')

    def render(self, text):
        self.__init__()
        return self.block(text)


def md_to_html(text):
    out = Markdown().render(text)
    # 正文视频默认 metadata 预加载, 不让整片视频阻塞首屏
    out = re.sub(r"<video\b(?![^>]*\bpreload=)", '<video preload="metadata"', out)
    return out


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


def load_notes():
    """笔记: content/notes/*.md, 零散知识与灵感速记, 生成 /notes/ 目录页与 /notes/<slug>/ 详情页"""
    nc = CONFIG.get("notes") or {}
    if not nc.get("enabled"):
        return []
    notes = []
    for fp in sorted((CONTENT / "notes").glob("*.md")):
        raw = fp.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw)
        if str(meta.get("draft", "")).lower() in ("true", "1", "yes"):
            continue
        date = parse_date(meta.get("date")) or datetime.date.fromtimestamp(fp.stat().st_mtime)
        slug = meta.get("slug") or fp.stem
        title = meta.get("title") or slug
        summary = meta.get("summary") or ""
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        tmp = Markdown()
        content_html = tmp.render(body)
        notes.append({
            "slug": slug,
            "title": title,
            "date": date,
            "date_str": date_fmt(date),
            "tags": tags,
            "summary": summary,
            "url": f"notes/{slug}/",
            "content_html": content_html,
            "content_text": re.sub(r"<[^>]+>", "", content_html),
            "headings": tmp.headings,
        })
    notes.sort(key=lambda d: d["date"], reverse=True)
    return notes


def pin_badge():
    """置顶徽标 (复用), 保证全部列表里置顶可见而非摆设。
    SVG 图钉矢量图形替代旧 emoji, 随 currentColor 适配深浅色主题。"""
    svg = ('<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" '
           'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
           '<path d="M9 3.5h6l-0.9 6.4 3.4 3.4v2.2H6.5v-2.2l3.4-3.4L9 3.5z"/><path d="M12 15.5V21"/></svg>')
    return f'<span class="pin-badge" title="置顶文章">{svg}<i>置顶</i></span>'


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

def seo_meta(title, description, page_url="", page_type="website", date_iso="", image=""):
    """生成 canonical + Open Graph + Twitter Card + JSON-LD 结构化数据。
    page_url 为站内相对路径(如 posts/x/); 空串 = 首页。"""
    base = SITE.get("base", "").rstrip("/") + "/"
    absolute = base if not page_url else base + page_url.lstrip("/")
    cfg = CONFIG.get("seo") or {}
    default_img = cfg.get("og_image") or "static/img/favicon.svg"
    img = image or default_img
    if img and not img.startswith(("http://", "https://")):
        img = base + img.lstrip("/")
    lang = SITE.get("language", "zh-CN")
    h = [f'<link rel="canonical" href="{esc(absolute)}">']
    h.append(f'<meta property="og:type" content="{esc(page_type)}">')
    h.append(f'<meta property="og:title" content="{esc(title)}">')
    h.append(f'<meta property="og:description" content="{esc(description)}">')
    h.append(f'<meta property="og:url" content="{esc(absolute)}">')
    h.append(f'<meta property="og:site_name" content="{esc(SITE.get("title", ""))}">')
    h.append(f'<meta property="og:locale" content="{esc(lang.replace("-", "_"))}">')
    h.append('<meta name="twitter:card" content="summary_large_image">')
    h.append(f'<meta name="twitter:title" content="{esc(title)}">')
    h.append(f'<meta name="twitter:description" content="{esc(description)}">')
    if cfg.get("twitter_handle"):
        h.append(f'<meta name="twitter:site" content="{esc(cfg["twitter_handle"])}">')
    if img:
        h.append(f'<meta property="og:image" content="{esc(img)}">')
        h.append(f'<meta name="twitter:image" content="{esc(img)}">')
    if page_type == "article":
        ld = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": title,
            "description": description,
            "url": absolute,
            "mainEntityOfPage": {"@type": "WebPage", "@id": absolute},
            "inLanguage": lang,
            "author": {"@type": "Person", "name": SITE.get("author", "")},
            "publisher": {"@type": "Organization", "name": SITE.get("title", ""),
                          "logo": {"@type": "ImageObject", "url": img}},
        }
        if date_iso:
            ld["datePublished"] = date_iso + "T00:00:00+08:00"
            ld["dateModified"] = date_iso + "T00:00:00+08:00"
    elif page_type == "website":
        ld = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": SITE.get("title", ""),
            "description": SITE.get("description", ""),
            "url": base,
            "inLanguage": lang,
        }
    else:
        ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "description": description,
            "url": absolute,
            "inLanguage": lang,
        }
    h.append(f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>')
    return "\n".join(h)


# ------------------------------------------------------------ 侧栏数据层 ----

def sidebar_cfg():
    return CONFIG.get("sidebar_right") or {}


def layout_css_vars():
    """文章卡片 / 正文内容尺寸: config.layout 注入 :root CSS 变量。
    由 Renderer.page 放入 extra_head, 位于 stylesheet link 之后, 覆盖 :root 默认值。"""
    ly = CONFIG.get("layout") or {}
    parts = ["--card-cover-h:%dpx" % max(60, int(ly.get("card_cover_height") or 150))]
    cw = (ly.get("card_width") or "").strip()
    if re.fullmatch(r"\d+(px|rem|em|%|vw)", cw):
        parts.append("--card-max-w:%s" % cw)
    cmw = max(420, int(ly.get("content_max_width") or 780))
    parts.append("--content-max-w:%dpx" % cmw)
    return "<style>:root{%s}</style>" % ";".join(parts)


def link_strategy_meta():
    """链接跳转策略: config.link_strategy -> meta, 运行期 viewer.js 读取执行。
    internal: self(站内当前页) / blank; external: blank / self。"""
    ls = CONFIG.get("link_strategy") or {}
    internal = "blank" if str(ls.get("internal", "")).lower() == "blank" else "self"
    external = "self" if str(ls.get("external", "")).lower() == "self" else "blank"
    data = json.dumps({"internal": internal, "external": external}, separators=(",", ":"))
    return f'<meta name="overcome-links" content=\'{data}\'>'


def right_bar_width():
    """右侧栏宽度(px), 由 config.sidebar_right.width 控制, 注入 CSS 变量"""
    try:
        w = int(sidebar_cfg().get("width") or 300)
    except (TypeError, ValueError):
        w = 300
    return 220 if w < 220 else (480 if w > 480 else w)


def toc_position():
    """文章目录位置: left(左侧栏) / right(右侧栏 widget) / hidden(隐藏)"""
    return (sidebar_cfg().get("toc_position") or "left").lower()


def sidebar_widgets(page_type):
    """解析某页面类型的右侧栏 widget 列表。
    优先 pages[page_type].widgets; 兼容旧布尔开关(show_latest/show_tags/show_archive);
    monitor 受独立开关(monitor.enabled/widget)约束, 在任何来源里都被过滤。"""
    cfg = sidebar_cfg()
    if not cfg.get("enabled"):
        return []
    spec = (cfg.get("pages") or {}).get(page_type)
    ws = None
    if isinstance(spec, dict):
        ws = spec.get("widgets")
    elif isinstance(spec, list):
        ws = spec
    if ws is None:
        ws = []
        if cfg.get("show_latest", True):
            ws.append("latest")
        if cfg.get("show_tags", True):
            ws.append("tags")
        if cfg.get("show_archive", True):
            ws.append("archive")
        mon = CONFIG.get("monitor") or {}
        if mon.get("enabled") and mon.get("widget", True):
            ws.append("monitor")
    if not isinstance(ws, list):
        ws = []
    mon = CONFIG.get("monitor") or {}
    if "monitor" in ws and not (mon.get("enabled") and mon.get("widget", True)):
        ws = [w for w in ws if w != "monitor"]
    return [w for w in ws if isinstance(w, str)]


def toc_html(headings, title="文章目录"):
    """渲染目录 HTML (侧栏部件), headings = [(level, anchor_id, text)]"""
    if not headings:
        return ""
    items = []
    for lv, aid, text in headings:
        cls = "toc-h3" if lv >= 3 else ""
        items.append(f'<a class="{cls}" href="#{aid}">{text}</a>')
    return ('<nav class="side-toc"><div class="side-toc-title">' + esc(title)
            + '</div><div class="side-toc-links">' + "".join(items) + "</div></nav>")


def friend_avatar(f):
    """友链头像: 配置 avatar 优先; 否则回退到站点 favicon 服务 (duckduckgo, 免费无 key)"""
    av = (f.get("avatar") or "").strip()
    if av:
        return esc(av)
    m = re.match(r"^https?://([^/]+)", (f.get("url") or "").strip())
    if m:
        return "https://icons.duckduckgo.com/ip3/%s.ico" % esc(m.group(1))
    return ""


def friend_avatar_html(f):
    """友链头像 HTML: 配置 avatar 优先, 否则 favicon 服务; 加载失败回退首字母占位"""
    av = friend_avatar(f)
    ph = esc((f.get("name") or "友")[0])
    if av:
        return (f'<span class="friend-avatar"><img src="{av}" alt="" loading="lazy" decoding="async" '
                f'onerror="this.style.display=\'none\';var s=this.nextElementSibling;if(s){{s.style.display=\'flex\';}}">'
                f'<span class="avatar-ph" style="display:none">{ph}</span></span>')
    return f'<span class="friend-avatar"><span class="avatar-ph">{ph}</span></span>'


def render_circle_block(circle):
    """友链朋友圈: 聚合各友链 RSS 最新条目展示; friend_rss.enabled 控制开关"""
    fr = CONFIG.get("friend_rss") or {}
    if not fr.get("enabled"):
        return ""
    max_items = max(1, int(fr.get("max_items", 5)))
    blocks = []
    for f, items in circle:
        rows = []
        for it in items[:max_items]:
            link = (it.get("link") or "").strip()
            title = (it.get("title") or link).strip()
            if not link or not title:
                continue
            rows.append(f'<li><a href="{esc(link)}" target="_blank" rel="noopener nofollow">{esc(title)}</a>'
                        f'<span class="w-date">{esc(it.get("pub") or "")}</span></li>')
        if not rows:
            continue
        head = (f'<div class="circle-head">{friend_avatar_html(f)}'
                f'<a href="{esc(f.get("url", "#"))}" target="_blank" rel="noopener nofollow"><b>{esc(f.get("name", ""))}</b></a>')
        if (f.get("rss") or "").strip():
            head += f'<a class="circle-feed" href="{esc(f["rss"])}" target="_blank" rel="noopener nofollow" title="订阅该友链 RSS">RSS</a>'
        head += "</div>"
        blocks.append(f'<div class="circle-friend">{head}<ul class="widget-list">{"".join(rows)}</ul></div>')
    if not blocks:
        return ('<section class="friend-circle"><h3 class="widget-h">友链朋友圈</h3>'
                '<p class="circle-empty">暂无动态：为友链配置 RSS 订阅地址后，这里会自动聚合他们的最新文章。</p></section>')
    return ('<section class="friend-circle"><h3 class="widget-h">友链朋友圈</h3>'
            '<div class="circle-grid">' + "".join(blocks) + "</div></section>")


# 署名标准值: Powered by 科技酱 & OverCome (不可移除/修改/篡改/遮掩)
# 任何对 config.footer.powered_by 的改动都会让构建直接失败, 站点无法上线。
SIGN_STANDARD = {
    "tj_name": "科技酱", "tj_url": "https://docs.asoe.cn",
    "oc_name": "OverCome", "oc_url": "https://github.com/techjiang/OverCome",
}


def assert_standard_sign():
    """署名锁定为标准值: 修改 config 即构建崩溃 (不可修改/篡改防线之二)"""
    pb = (CONFIG.get("footer") or {}).get("powered_by") or {}
    tj, oc = pb.get("techjiang") or {}, pb.get("overcome") or {}
    got = [str(tj.get("name", "")), str(tj.get("url", "")),
           str(oc.get("name", "")), str(oc.get("url", ""))]
    want = [SIGN_STANDARD["tj_name"], SIGN_STANDARD["tj_url"],
            SIGN_STANDARD["oc_name"], SIGN_STANDARD["oc_url"]]
    if got != want:
        raise SystemExit("[FATAL] 署名配置被修改: Powered by 科技酱 & OverCome 不可修改/篡改, 站点拒绝构建.")


def powered_by_spec():
    """署名规格: [名称1, 链接1, 名称2, 链接2] — 固定标准值, 与页面 DOM/校验脚本一致"""
    return [SIGN_STANDARD["tj_name"], SIGN_STANDARD["tj_url"],
            SIGN_STANDARD["oc_name"], SIGN_STANDARD["oc_url"]]


def seal_token():
    """署名完整性令牌: 由站点身份与署名规格派生 (构建期固定)。
    前端 seal.js 校验 meta 与 .powered-by 一致性; 构建期也用它反校验产物。"""
    import hashlib
    spec = powered_by_spec()
    raw = "|".join([SITE.get("base", ""), SITE.get("title", "")] + list(spec))
    return hashlib.sha256(("overcome-seal-v5:" + raw).encode("utf-8")).hexdigest()[:24]


def seal_meta():
    """署名校验 meta: 规格 + 令牌, 注入每个页面 head。"""
    spec = powered_by_spec()
    spec_txt = "|".join(spec)
    return (f'<meta name="overcome-seal-spec" content="{esc(spec_txt)}">\n'
            f'<meta name="overcome-seal" content="{seal_token()}">')


def powered_by_html():
    """文章底部署名: Powered by <a>科技酱</a> & <a>OverCome</a>。
    署名不可移除、修改、篡改、遮掩:
      1) 构建期: verify_build_integrity() 校验产物, 缺少即构建失败 (网站无法上线);
      2) 运行期: seal.js 校验 DOM/链接/可见性, 不通过即展示崩溃页。
    因此即使配置 enabled=false 也会强制渲染。"""
    tj_name, tj_url, oc_name, oc_url = powered_by_spec()
    tj_name_e, oc_name_e = esc(tj_name), esc(oc_name)
    tj_url_e, oc_url_e = esc(tj_url), esc(oc_url)
    tj_html = f'<a href="{tj_url_e}" data-overcome-link="1">{tj_name_e}</a>' if tj_url_e else tj_name_e
    oc_html = f'<a href="{oc_url_e}" data-overcome-link="1">{oc_name_e}</a>' if oc_url_e else oc_name_e
    return (f'<p class="powered-by" data-overcome-sign="1">Powered by {tj_html} & {oc_html}</p>')


def verify_build_integrity():
    """构建期署名完整性校验 (防移除防线):
    扫描全部 dist 产物 HTML, 任一页面缺少署名/校验 meta/不匹配即构建崩溃。
    从 build.py 删除署名生成逻辑 = 构建必然失败 = 站点无法部署使用。"""
    spec = powered_by_spec()
    tok = seal_token()
    dist_html = [fp for fp in DIST.rglob("*.html")
                 if "go/" not in str(fp.relative_to(DIST)) and fp.name not in ("404.html",)]
    if not dist_html:
        return
    bad = []
    for fp in dist_html:
        txt = fp.read_text(encoding="utf-8")
        if 'data-overcome-sign="1"' not in txt or "Powered by" not in txt:
            bad.append((fp.name, "缺少署名节点"))
            continue
        if f'name="overcome-seal" content="{tok}"' not in txt:
            bad.append((fp.name, "署名校验令牌缺失或不匹配"))
            continue
        if f'name="overcome-seal-spec" content="{esc("|".join(spec))}"' not in txt:
            bad.append((fp.name, "署名规格缺失或不匹配"))
            continue
        link1, link2 = spec[1], spec[3]
        if link1 and f'href="{esc(link1)}"' not in txt:
            bad.append((fp.name, "署名链接被修改"))
        if link2 and f'href="{esc(link2)}"' not in txt:
            bad.append((fp.name, "署名链接被修改"))
    if bad:
        detail = "; ".join(f"{n} -> {r}" for n, r in bad[:6])
        raise SystemExit(f"[FATAL] 署名完整性校验失败: {detail} (署名不可移除/修改/篡改, 站点拒绝构建)")
    # 校验运行期防线脚本未被改动 (seal.js 内置标准署名 EXPEC, 改动即构建失败)
    seal_fp = DIST / "static" / "js" / "seal.js"
    if seal_fp.exists():
        seal_txt = seal_fp.read_text(encoding="utf-8")
        expect_marker = "科技酱|https://docs.asoe.cn|OverCome|https://github.com/techjiang/OverCome"
        if expect_marker not in seal_txt:
            raise SystemExit("[FATAL] 运行期署名防线 seal.js 缺失/被改动, 站点拒绝构建.")
    else:
        raise SystemExit("[FATAL] 运行期署名防线 seal.js 缺失, 站点拒绝构建.")
    print(f"[OK] 署名完整性校验通过: 共 {len(dist_html)} 个页面均含受保护署名")


# ------------------------------------------------- 友链朋友圈 (RSS 聚合) ----

def _local(tag):
    """取 XML 标签的本地名 (兼容 {namespace}tag / tag)"""
    return tag.rsplit("}", 1)[-1] if tag else ""


def _feed_child(node, names):
    """在元素子节点中按本地名匹配第一个 (兼容 RSS2/Atom/RDF 命名空间)"""
    for c in node:
        if c.tag and _local(c.tag) in names:
            return c
    return None


def _feed_text(node):
    if node is None or node.text is None:
        return ""
    return re.sub(r"\s+", " ", node.text).strip()


def parse_feed_bytes(data):
    """解析 RSS 2.0 / Atom 源, 返回 [{title, link, pub}], 最多 20 条"""
    root = ET.fromstring(data)
    items = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title = _feed_text(_feed_child(node, ["title"]))
        link = ""
        lc = _feed_child(node, ["link"])
        if lc is not None:
            link = lc.get("href") or lc.text or ""
            link = link.strip()
        pub = _feed_text(_feed_child(node, ["pubDate", "published", "updated", "date"]))
        if title or link:
            items.append({"title": title, "link": link, "pub": pub})
        if len(items) >= 20:
            break
    return items


def fetch_friend_circle(friends):
    """构建期抓取各友链 RSS (仅抓取配置了 rss 的友链), 失败安全降级。
    返回 (pairs, ok_count, total_count); 永不因网络错误中断构建。"""
    fr = CONFIG.get("friend_rss") or {}
    if not fr.get("enabled"):
        return [], 0, 0
    timeout = int(fr.get("fetch_timeout", 6))
    concurrency = max(1, int(fr.get("concurrency", 4)))
    candidates = [f for f in friends if (f.get("rss") or "").strip()
                  and (f.get("rss") or "").startswith(("http://", "https://"))]
    if not candidates:
        return [], 0, 0
    ok = [0]

    def grab(f):
        url = f["rss"].strip()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OverCome/%s (+%s)" % (SITE.get("title", ""), SITE.get("base", ""))})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read(300000)
            items = parse_feed_bytes(data)
            ok[0] += 1
            return (f, items)
        except Exception:
            return (f, [])

    pairs = []
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for res in ex.map(grab, candidates):
            pairs.append(res)
    return pairs, ok[0], len(candidates)


class Renderer:
    """root 前缀: 空 = 根目录页面; '../' = 一级子目录; '../../' = 二级子目录"""

    def __init__(self):
        self.base = (THEME / "templates" / "base.html").read_text(encoding="utf-8")
        self.nav = CONFIG.get("nav", [])
        self.social = CONFIG.get("social", {})
        self.dist = DIST

    def page(self, title, body, *, root, active="", description="", extra_head="", side_toc="", show_right=True, seo=None, page_type="home", toc="", rel=None):
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
        # 目录位置: left -> 左侧栏(side_toc); right -> 置入右侧栏首 widget; hidden -> 不渲染
        pos = toc_position()
        if pos == "hidden":
            side_toc, toc = "", ""
        elif pos == "right":
            side_toc = ""
        elif not side_toc and toc:
            side_toc = toc
        right_html = self.right_bar_html(root, page_type, toc=toc if pos == "right" else "", rel=rel) if show_right else ""
        if seo is None:
            seo = {}
        _surl = seo.get("url", "")
        _stype = seo.get("type", "website")
        _sdate = seo.get("date", "")
        _simg = seo.get("image", "")
        seo_head = seo_meta(title, description or SITE.get("description", ""),
                            _surl, _stype, _sdate, _simg)
        # 全局注入: 布局尺寸变量 + 链接跳转策略 + 署名完整性校验 (不可移除/篡改)
        extra_head = layout_css_vars() + link_strategy_meta() + seal_meta() + extra_head
        html = self.base.replace("{{title}}", esc(title)) \
            .replace("{{site_title}}", esc(SITE["title"])) \
            .replace("{{subtitle}}", esc(SITE.get("subtitle", ""))) \
            .replace("{{description}}", esc(description or SITE.get("description", ""))) \
            .replace("{{root}}", root) \
            .replace("{{nav}}", "".join(nav_html)) \
            .replace("{{social}}", social_html) \
            .replace("{{side_toc}}", side_toc) \
            .replace("{{right_bar}}", right_html) \
            .replace("{{right_w}}", str(right_bar_width())) \
            .replace("{{site_year}}", str(datetime.date.today().year)) \
            .replace("{{site_author}}", esc(SITE.get("author", ""))) \
            .replace("{{extra_head}}", extra_head) \
            .replace("{{seo_head}}", seo_head) \
            .replace("{{analytics}}", analytics_html()) \
            .replace("{{assets_version}}", assets_version()) \
            .replace("{{content}}", body + powered_by_html())
        # 插件后处理钩子: 逐页 process(html, context), 插件异常不阻塞主站构建
        for pl in load_plugins():
            mod = pl.get("module")
            if mod and callable(getattr(mod, "process", None)):
                try:
                    html = mod.process(html, {"page_type": page_type, "root": root, "title": title})
                except Exception:
                    pass
        return html

    def right_bar_html(self, root, page_type="home", toc="", rel=None):
        """右侧栏组件, widgets 顺序与内容由 config.sidebar_right.pages 定义
        支持: latest / tags / archive / monitor / toc / related"""
        ws = sidebar_widgets(page_type)
        if not ws:
            return ""
        if toc and "toc" not in ws:
            ws = ["toc"] + ws
        widgets = []
        for w in ws:
            if w == "latest":
                n = int(sidebar_cfg().get("latest_count", 5))
                # 置顶文章也进"最新文章"并带徽标, 让置顶不是摆设
                lst = _ALL_POSTS[:n]
                items = "".join(
                    f'<li>{pin_badge() if p.get("pinned") else ""}<a href="{root}{p["url"]}">{esc(p["title"])}</a><span class="w-date">{p["date_str"]}</span></li>'
                    for p in lst)
                if lst:
                    widgets.append(f'<div class="widget"><h3>最新文章</h3><ul class="widget-list">{items}</ul></div>')
            elif w == "tags":
                _, tags, _ = compute_indexes(_ALL_POSTS)
                top = sorted(tags.items(), key=lambda kv: -len(kv[1]))[:int(sidebar_cfg().get("tags_count", 16))]
                chips = "".join(
                    f'<a class="chip chip-tag" href="{root}tags/{slugify(t)}/">{esc(t)}<em>{len(ps)}</em></a>'
                    for t, ps in top)
                if chips:
                    widgets.append(f'<div class="widget"><h3>标签</h3><div class="widget-tags">{chips}</div></div>')
            elif w == "archive":
                widgets.append(
                    f'<div class="widget"><h3>归档</h3><ul class="widget-list"><li><a href="{root}archive/">全部文章 ({len(_ALL_POSTS)})</a><span class="w-date">{SITE["since"]} 至今</span></li></ul></div>')
            elif w == "monitor":
                mon = CONFIG.get("monitor") or {}
                targets = json.dumps(mon.get("targets", []), ensure_ascii=False)
                widgets.append(f'''<div class="widget"><h3>站点监测</h3>
<div class="monitor" id="monitor-box" data-targets='{targets}'></div>
<script src="{root}static/js/monitor.js?v={assets_version()}" defer></script></div>''')
            elif w == "toc" and toc:
                widgets.append(f'<div class="widget widget-toc">{toc}</div>')
            elif w == "related" and rel:
                items = "".join(
                    f'<li><a href="{root}posts/{p["slug"]}/">{esc(p["title"])}</a><span class="w-date">{p["date_str"]}</span></li>'
                    for p in rel)
                if items:
                    widgets.append(f'<div class="widget"><h3>相关阅读</h3><ul class="widget-list">{items}</ul></div>')
            elif w.startswith("custom:"):
                cid = w.split(":", 1)[1]
                w_html = custom_widget_html(root, cid)
                if w_html:
                    widgets.append(w_html)
            elif w.startswith("plugin:"):
                cid = w.split(":", 1)[1]
                w_html = custom_widget_html(root, "plugin:" + cid)
                if w_html:
                    widgets.append(w_html)
        if not widgets:
            return ""
        return '<aside class="right-bar" aria-label="侧边栏">' + "".join(widgets) + "</aside>"


# ------------------------------------------------------------ 插件生态 ----

_PLUGIN_CACHE = None


def load_plugins():
    """插件生态: 扫描 plugins/<name>/plugin.json (+ 可选 Python 入口) 并加载。
    每条插件元数据: {name, version, description, author, entry(hooks 所在模块文件), registry(注册表页展示)}
    Python 入口约定钩子 (可选实现):
      process(html, context) -> html   逐页后处理, context={page_type, root, title}
      widget(context) -> str           右侧栏自定义组件 HTML, context={root, page_type}
      register_pages() -> [(path, html)]  构建期注册额外静态页面
    插件在构建机器本地执行, 仅安装/信任你自己编写的插件。"""
    global _PLUGIN_CACHE
    if _PLUGIN_CACHE is not None:
        return _PLUGIN_CACHE
    _PLUGIN_CACHE = []
    pc = CONFIG.get("plugins") or {}
    if not pc.get("enabled"):
        return _PLUGIN_CACHE
    pdir = ROOT / (pc.get("path") or "plugins")
    if not pdir.is_dir():
        return _PLUGIN_CACHE
    for d in sorted(pdir.iterdir()):
        if not d.is_dir():
            continue
        jp = d / "plugin.json"
        if not jp.exists():
            continue
        try:
            meta = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta.setdefault("name", d.name)
        meta.setdefault("version", "0.1.0")
        meta.setdefault("description", "")
        meta.setdefault("author", SITE.get("author", ""))
        mod = None
        py = d / (meta.get("entry") or "plugin.py")
        if py.exists():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "overcome_plugin_" + re.sub(r"\W", "_", d.name), py)
                if spec is not None and spec.loader is not None:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
            except Exception:
                mod = None
        _PLUGIN_CACHE.append({"dir": d.name, "meta": meta, "module": mod})
    return _PLUGIN_CACHE


def plugin_pages():
    """调用各插件的 register_pages() 钩子, 返回 [(path, html)] 供 build() 写入"""
    out = []
    for pl in load_plugins():
        mod = pl.get("module")
        if not mod or not callable(getattr(mod, "register_pages", None)):
            continue
        try:
            pages = mod.register_pages() or []
            out.extend((str(p), str(h)) for p, h in pages if p and h)
        except Exception:
            pass
    return out


def custom_widget_html(root, cid):
    """自定义侧栏组件: config.custom_widgets 中 id 匹配的组件。
    type=html 直接内联; text 文本; list 列表; plugin 交给同名插件的 widget 钩子。"""
    if cid.startswith("plugin:"):
        pname = cid.split(":", 1)[1]
        for pl in load_plugins():
            if pl["dir"] != pname:
                continue
            mod = pl.get("module")
            if mod and callable(getattr(mod, "widget", None)):
                try:
                    w = mod.widget({"root": root, "page_type": "custom"})
                    if w:
                        return f'<div class="widget widget-plugin widget-{esc(pname)}">{w}</div>'
                except Exception:
                    pass
            return ""
        return ""
    for w in CONFIG.get("custom_widgets") or []:
        if w.get("id") != cid:
            continue
        title = esc(w.get("title") or "组件")
        wtype = w.get("type") or "html"
        if wtype == "text":
            inner = f'<p class="custom-widget-text">{esc(w.get("text", ""))}</p>'
        elif wtype == "list":
            items = "".join(f'<li><a href="{esc(it.get("url", "#"))}">{esc(it.get("label", ""))}</a></li>'
                            for it in w.get("items") or [])
            inner = f'<ul class="widget-list">{items}</ul>'
        else:
            inner = w.get("html") or ""
        return f'<div class="widget widget-custom widget-{esc(cid)}"><h3>{title}</h3>{inner}</div>'
    return ""


def analytics_html():
    """站点统计脚本注入 (不蒜子 / 自定义脚本), 默认关闭"""
    cfg = CONFIG.get("analytics") or {}
    if not cfg.get("enabled"):
        return ""
    provider = cfg.get("provider", "")
    script = cfg.get("script", "")
    if provider == "busuanzi":
        return '''<link rel="preconnect" href="https://busuanzi.ibruce.info" crossorigin>
<div class="site-stats" aria-label="站点统计">
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
    data-loading="lazy" decoding="async"
    crossorigin="anonymous" async>
  </script>
</section>'''


def render_index(posts, page_no=1, per_page=10):
    r = Renderer()
    total = len(posts)
    pages = max(1, (total + per_page - 1) // per_page)
    page_no = max(1, min(page_no, pages))
    start = (page_no - 1) * per_page
    chunk = posts[start:start + per_page]

    root = "" if page_no == 1 else "../../"
    cards = []
    for p in chunk:
        badge = pin_badge()
        tags_html = "".join(
            f'<a class="chip chip-tag" href="{root}tags/{slugify(t)}/">{esc(t)}</a>'
            for t in p["tags"][:4])
        cover_html = ""
        if p.get("cover"):
            cover_html = f'<div class="card-cover"><img src="{esc(p["cover"])}" alt="" loading="lazy" decoding="async"></div>'
        else:
            cover_html = '<div class="card-cover card-cover-placeholder"><span></span></div>'
        pin_class = " card-has-pin" if p.get("pinned") else ""
        cards.append(f'''
<article class="card{pin_class}">
  {cover_html}
  <div class="card-body">
    <div class="card-meta">
      <span class="date">{p["date_str"]}</span>
      <a class="chip chip-cat" href="{root}categories/{slugify(p["category"])}/">{esc(p["category"])}</a>
      <span class="read-min">{p["reading_min"]} 分钟阅读 · {p["word_count"]} 字</span>
    </div>
    <h2 class="card-title">{badge}<a href="{root}{p["url"]}">{esc(p["title"])}</a></h2>
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
        # 页码导航 (每页 posts_per_page 篇, 页码可直跳)
        page_btns = []
        for pn in range(1, pages + 1):
            if pn == page_no:
                page_btns.append(f'<span class="page-num cur" aria-current="page">{pn}</span>')
            elif pn == 1:
                page_btns.append(f'<a class="page-num" href="{root}index.html">{pn}</a>')
            else:
                page_btns.append(f'<a class="page-num" href="{root}page/{pn}/">{pn}</a>')
        items.append('<span class="page-nums">' + "".join(page_btns) + "</span>")
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
                    fcov = f'<img src="{esc(p["cover"])}" alt="" loading="lazy" decoding="async">'
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
                  description=SITE.get("description", ""),
                  seo={"url": "", "type": "website"})


def render_post(post, posts):
    r = Renderer()
    root = "../../"
    prev = next_p = None
    for idx, p in enumerate(posts):
        if p["slug"] == post["slug"]:
            prev = posts[idx + 1] if idx + 1 < len(posts) else None   # 更早的
            next_p = posts[idx - 1] if idx > 0 else None              # 更新的
            break

    toc = toc_html(post["headings"], "文章目录")

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
                  description=post.get("summary", ""), toc=toc, page_type="post", rel=rel,
                  extra_head=f'<link rel="stylesheet" href="../../static/css/highlight.css?v={assets_version()}">',
                  seo={"url": "posts/%s/" % post["slug"], "type": "article",
                       "date": post["date"].isoformat(), "image": post.get("cover", "")})


def render_page(page):
    r = Renderer()
    body = f'<article class="page post"><header class="post-header"><h1 class="page-title">{esc(page["title"])}</h1></header><div class="post-body">{page["content_html"]}</div></article>'
    surl = "" if page["slug"] == "index" else page["slug"] + "/"
    return r.page(page["title"], body, root="../", active="page", description=SITE.get("description", ""),
                  page_type="page",
                  seo={"url": surl, "type": "webpage"})


def render_archive(posts):
    r = Renderer()
    _, _, archive = compute_indexes(posts)
    html_parts = []
    for key in sorted(archive.keys(), reverse=True):
        items = "".join(
            f'<li><span class="date">{p["date_str"]}</span>{pin_badge() if p.get("pinned") else ""}<a href="../posts/{p["slug"]}/">{esc(p["title"])}</a><span class="cat">{esc(p["category"])}</span></li>'
            for p in archive[key])
        html_parts.append(f'<section class="archive-group"><h2>{esc(key)} <em>{len(archive[key])}</em></h2><ul>{items}</ul></section>')
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">归档</h1><p class="page-sub">共 {len(posts)} 篇文章</p></header><div class="archive">{"".join(html_parts)}</div></div>'
    return r.page("归档", body, root="../", active="archive", page_type="archive", seo={"url": "archive/"})


def render_tags(posts):
    r = Renderer()
    _, tags, _ = compute_indexes(posts)
    items = []
    for tag, ps in sorted(tags.items(), key=lambda kv: -len(kv[1])):
        size = 1 + min(2, len(ps) // 3)
        items.append(f'<a class="tag-cloud tag-{size}" href="../tags/{slugify(tag)}/">{esc(tag)}<em>{len(ps)}</em></a>')
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">标签</h1></header><div class="tag-cloud-wrap">{"".join(items)}</div></div>'
    return r.page("标签", body, root="../", active="tags", page_type="tags", seo={"url": "tags/"})


def render_tag(tag, posts):
    r = Renderer()
    root = "../../"
    items = "".join(
        f'<li><span class="date">{p["date_str"]}</span>{pin_badge() if p.get("pinned") else ""}<a href="{root}posts/{p["slug"]}/">{esc(p["title"])}</a></li>'
        for p in posts)
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">#{esc(tag)}</h1><p class="page-sub">{len(posts)} 篇文章</p></header><ul class="flat-list">{items}</ul></div>'
    return r.page(f"标签: {tag}", body, root=root, active="tags", page_type="tags", seo={"url": f"tags/{slugify(tag)}/"})


def render_category(cat, posts):
    r = Renderer()
    root = "../../"
    items = "".join(
        f'<li><span class="date">{p["date_str"]}</span>{pin_badge() if p.get("pinned") else ""}<a href="{root}posts/{p["slug"]}/">{esc(p["title"])}</a></li>'
        for p in posts)
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">{esc(cat)}</h1><p class="page-sub">{len(posts)} 篇文章</p></header><ul class="flat-list">{items}</ul></div>'
    return r.page(f"分类: {cat}", body, root=root, active="", page_type="category", seo={"url": f"categories/{slugify(cat)}/"})


def render_search():
    r = Renderer()
    body = f'''<div class="page post"><header class="post-header"><h1 class="page-title">搜索</h1></header>
<div class="search-box"><input id="search-input" type="search" placeholder="输入关键词，如：Markdown、部署…" autocomplete="off"><button id="search-btn" type="button">搜索</button></div>
<div id="search-hint" class="search-hint">输入关键词即可全文检索本站内容</div>
<ul id="search-results" class="search-results"></ul></div>
<script src="../static/js/search.js?v={assets_version()}" defer></script>'''
    return r.page("搜索", body, root="../", active="search", show_right=False, seo={"url": "search/"})


def render_404():
    r = Renderer()
    body = '<div class="page post notfound"><h1 class="page-title">404</h1><p class="hero-sub">页面不存在或已被移动。</p><a class="btn" href="index.html">返回首页</a></div>'
    return r.page("页面未找到", body, root="", active="", show_right=False,
                  extra_head='<meta name="robots" content="noindex">')


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
    return r.page("文档", body, root="../", active="docs", page_type="doc", seo={"url": "docs/"})


def render_doc(doc, docs):
    """文档详情页 /docs/<slug>/: 含目录与文档内前后篇"""
    r = Renderer()
    root = "../../"
    toc = toc_html(doc["headings"], "文档目录")
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
                  description=doc.get("summary", ""), toc=toc, page_type="doc",
                  seo={"url": "docs/%s/" % doc["slug"], "type": "article",
                       "date": doc["date"].isoformat() if doc.get("date") else ""})


# ------------------------------------------------------------ 笔记 ----

def render_notes_index(notes):
    """笔记目录页 /notes/: 列表展示 + 每页 per_page 条分页"""
    r = Renderer()
    nc = CONFIG.get("notes") or {}
    per = max(1, int(nc.get("per_page", 10)))
    total = len(notes)
    pages = max(1, (total + per - 1) // per)
    page_no = 1
    chunk = notes[:per]
    items = "".join(
        f'<li><span class="date">{n["date_str"]}</span><a href="../{n["url"]}">{esc(n["title"])}</a><span class="cat">{esc(n.get("summary") or "笔记")}</span></li>'
        for n in chunk) or '<li class="empty">暂无笔记，将零散知识写进 content/notes/ 即可展示。</li>'
    pagination = ""
    if pages > 1:
        pagination = (f'<nav class="pagination"><span class="pager-info">{page_no} / {pages} · 共 {total} 篇笔记</span>'
                      f'<a class="pager next" href="../notes/">下一页 ›</a></nav>')
    body = (f'<div class="page post"><header class="post-header"><h1 class="page-title">笔记'
            f'</h1><p class="page-sub">{nc.get("subtitle", "零散知识与灵感的速记仓库")} · 共 {total} 篇</p></header>'
            f'<ul class="flat-list">{items}</ul>{pagination}</div>')
    return r.page("笔记", body, root="../", active="notes", page_type="notes", seo={"url": "notes/"})


def render_note(note, notes):
    """笔记详情页 /notes/<slug>/: 含目录、前后篇、侧栏"""
    r = Renderer()
    root = "../../"
    toc = toc_html(note["headings"], "笔记目录")
    prev = next_n = None
    for idx, n in enumerate(notes):
        if n["slug"] == note["slug"]:
            prev = notes[idx + 1] if idx + 1 < len(notes) else None
            next_n = notes[idx - 1] if idx > 0 else None
            break
    prev_html = f'<a class="nav-item prev" href="{root}{prev["url"]}"><span>← 上一篇</span><b>{esc(prev["title"])}</b></a>' if prev else "<span></span>"
    next_html = f'<a class="nav-item next" href="{root}{next_n["url"]}"><span>下一篇 →</span><b>{esc(next_n["title"])}</b></a>' if next_n else "<span></span>"
    tags_html = "".join(
        f'<a class="chip chip-tag" href="{root}tags/{slugify(t)}/">{esc(t)}</a>'
        for t in note["tags"])
    article = f'''
<article class="post">
  <header class="post-header">
    <div class="post-meta">
      <span class="date">{note["date_str"]}</span>
      <a class="crumb" href="../../notes/">← 返回笔记</a>
    </div>
    <h1 class="post-title">{esc(note["title"])}</h1>
    <div class="post-tags">{tags_html}</div>
  </header>
  <div class="post-layout">
    <div class="post-body">{note["content_html"]}</div>
  </div>
  <footer class="post-footer"><nav class="post-nav">{prev_html}{next_html}</nav></footer>
</article>'''
    return r.page(note["title"], article, root=root, active="notes",
                  description=note.get("summary", ""), toc=toc, page_type="note",
                  seo={"url": "notes/%s/" % note["slug"], "type": "article",
                       "date": note["date"].isoformat()})


# ------------------------------------------------------------ 动态 ----

def parse_dt(s, date_only=False):
    """解析动态时间: 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM', 失败返回 None"""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", s)
    if not m:
        return None
    try:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if date_only:
            return d
        hh, mm = int(m.group(4) or 0), int(m.group(5) or 0)
        return datetime.datetime(d.year, d.month, d.day, hh, mm)
    except ValueError:
        return None


def dynamic_entries(posts, notes):
    """动态时间线数据: config.dynamic.items + 自动并入最新文章/笔记发布。
    像朋友圈一样: 做了一件什么事 -> 以事件卡片呈现, 按时间倒序。"""
    dc = CONFIG.get("dynamic") or {}
    if not dc.get("enabled"):
        return []
    entries = []
    for it in dc.get("items") or []:
        dt = parse_dt(it.get("date"))
        if dt is None:
            continue
        entries.append({
            "ts": dt,
            "type": str(it.get("type") or "update"),
            "text": str(it.get("text") or ""),
            "link": it.get("link") or "",
            "title": it.get("title") or "",
            "source": "config",
        })
    if dc.get("include_posts"):
        for p in posts[:8]:
            if not p.get("date"):
                continue
            entries.append({
                "ts": datetime.datetime(p["date"].year, p["date"].month, p["date"].day, 12, 0),
                "type": "post",
                "text": f'发布了新文章《{p["title"]}》',
                "link": p["url"],
                "title": p["title"],
                "source": "post",
            })
    if dc.get("notes_sync"):
        for n in notes[:5]:
            if not n.get("date"):
                continue
            entries.append({
                "ts": datetime.datetime(n["date"].year, n["date"].month, n["date"].day, 12, 0),
                "type": "note",
                "text": f'新笔记：《{n["title"]}》',
                "link": n["url"],
                "title": n["title"],
                "source": "note",
            })
    entries.sort(key=lambda e: e["ts"], reverse=True)
    return entries


_TYPE_LABEL = {
    "release": ("版本更新", "release"),
    "milestone": ("里程碑", "milestone"),
    "update": ("动态", "update"),
    "post": ("发布文章", "post"),
    "note": ("新笔记", "note"),
}


def render_dynamic(posts, notes):
    """动态页 /dynamic/: 朋友圈式时间线"""
    r = Renderer()
    dc = CONFIG.get("dynamic") or {}
    entries = dynamic_entries(posts, notes)
    if not entries:
        body = '<div class="page post"><header class="post-header"><h1 class="page-title">动态</h1></header><p class="empty">暂无动态。</p></div>'
        return r.page("动态", body, root="../", active="dynamic", page_type="dynamic", seo={"url": "dynamic/"})
    items_html = []
    for e in entries:
        label, cls = _TYPE_LABEL.get(e["type"], (e["type"], "update"))
        t = esc(e["text"])
        ts = e["ts"]
        ts_txt = ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, datetime.datetime) else ts.strftime("%Y-%m-%d")
        if e.get("link"):
            t = f'<a href="../{esc(e["link"])}">{t}</a>'
        items_html.append(
            f'<li class="tl-item tl-{esc(cls)}">'
            f'<div class="tl-line" aria-hidden="true"><span class="tl-dot"></span></div>'
            f'<div class="tl-card"><div class="tl-head">'
            f'<span class="tl-badge">{esc(label)}</span><time class="tl-time">{ts_txt}</time></div>'
            f'<div class="tl-text">{t}</div></div></li>')
    title = esc(dc.get("title") or "动态")
    sub = esc(dc.get("subtitle") or "站点新鲜事，像朋友圈一样的时间线")
    body = (f'<div class="page post"><header class="post-header"><h1 class="page-title">{title}'
            f'</h1><p class="page-sub">{sub}</p></header>'
            f'<ul class="timeline">{ "".join(items_html) }</ul></div>')
    return r.page(title, body, root="../", active="dynamic", page_type="dynamic", seo={"url": "dynamic/"})


# ------------------------------------------------------------ 插件页 ----

def render_plugins_index():
    """插件注册表页 /plugins/: 展示已加载插件生态"""
    r = Renderer()
    pls = load_plugins()
    pc = CONFIG.get("plugins") or {}
    if not pls:
        empty = ('<p class="empty">尚未安装插件。在仓库根目录创建 <code>plugins/&lt;名称&gt;/plugin.json</code> '
                 '即可接入生态，详见 <a href="../docs/">文档</a>。</p>')
        body = (f'<div class="page post"><header class="post-header"><h1 class="page-title">插件'
                f'</h1><p class="page-sub">插件生态 · 构建期扩展钩子</p></header>{empty}</div>')
        return r.page("插件", body, root="../", active="plugins", page_type="plugins", seo={"url": "plugins/"})
    cards = []
    for pl in pls:
        meta = pl["meta"]
        caps = []
        mod = pl.get("module")
        if mod:
            for hook in ("process", "widget", "register_pages"):
                if callable(getattr(mod, hook, None)):
                    caps.append(hook)
        caps_txt = "".join(f'<span class="chip chip-tag">{esc(c)}</span>' for c in caps) or '<span class="chip chip-tag">无钩子</span>'
        cards.append(f'''
<li class="plugin-card">
  <div class="plugin-head">
    <b>{esc(meta.get("name", ""))}</b>
    <span class="plugin-ver">v{esc(meta.get("version", ""))}</span>
  </div>
  <p class="plugin-desc">{esc(meta.get("description", ""))}</p>
  <p class="plugin-meta">作者：{esc(meta.get("author", ""))} · 目录：plugins/{esc(pl["dir"])}</p>
  <div class="plugin-caps">{caps_txt}</div>
</li>''')
    body = (f'<div class="page post"><header class="post-header"><h1 class="page-title">插件'
            f'</h1><p class="page-sub">插件生态 · {len(pls)} 个已加载 · 构建期扩展钩子</p></header>'
            f'<ul class="plugin-list">{"".join(cards)}</ul></div>')
    return r.page("插件", body, root="../", active="plugins", page_type="plugins", seo={"url": "plugins/"})


def render_links(friends, submit_url="", circle=None):
    """友链页 /links/: 展示友链(带头像) + 友链朋友圈(RSS聚合) + 站内自助提交表单"""
    r = Renderer()
    root = "../"
    if not friends:
        items = '<li class="empty">暂无友链，欢迎申请加入。</li>'
    else:
        cards = []
        for f in friends:
            cards.append(f'''
<li class="friend-card">
  {friend_avatar_html(f)}
  <div class="friend-meta">
    <a href="{esc(f.get("url", "#"))}" target="_blank" rel="noopener nofollow"><b>{esc(f.get("name", ""))}</b></a>
    <p>{esc(f.get("desc", ""))}</p>
  </div>
</li>''')
        items = "".join(cards)
    circle_block = render_circle_block(circle or [])
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
    body = f'<div class="page post"><header class="post-header"><h1 class="page-title">友情链接</h1><p class="page-sub">共 {len(friends)} 位伙伴</p></header><ul class="friend-list">{items}</ul>{circle_block}{submit_block}{form_html}</div>'
    return r.page("友情链接", body, root=root, active="links", page_type="links", seo={"url": "links/"})


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
    return r.page(title, body, root=root, active="", description=note, page_type="page",
                  seo={"url": "forms/" + slug + "/"})


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

def _feed_dt(d):
    if not d:
        d = datetime.date.today()
    return d.isoformat() + "T00:00:00+08:00"


def _cd(text):
    """CDATA 包裹, 并转义内部的 ]]> 避免提前闭合"""
    return "<![CDATA[" + str(text).replace("]]>", "]]]]><![CDATA[>") + "]]>"


def render_feed(posts):
    base = SITE.get("base", "").rstrip("/") + "/"
    today = datetime.date.today().isoformat() + "T00:00:00+08:00"
    pub = _feed_dt(posts[0]["date"]) if posts else today
    entries = []
    for p in posts[:20]:
        desc = p.get("summary") or p["content_text"][:200]
        full = p["content_html"]
        entries.append(f'''<entry>
  <title>{esc(p["title"])}</title>
  <link href="{base}{p["url"]}"/>
  <id>{base}{p["url"]}</id>
  <guid isPermaLink="true">{base}{p["url"]}</guid>
  <published>{_feed_dt(p["date"])}</published>
  <updated>{_feed_dt(p["date"])}</updated>
  <author><name>{esc(SITE.get("author", ""))}</name><email>{esc(SITE.get("email", ""))}</email></author>
  <category term="{esc(p["category"])}"/>
  <summary>{esc(desc)}</summary>
  <content type="html">{_cd(full)}</content>
</entry>''')
    site_email = f'<email>{esc(SITE.get("email", ""))}</email>' if SITE.get("email") else ""
    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <title>{esc(SITE["title"])}</title>
  <subtitle>{esc(SITE.get("description", ""))}</subtitle>
  <link href="{base}"/>
  <link href="{base}feed.xml" rel="self"/>
  <updated>{today}</updated>
  <id>{base}</id>
  <author><name>{esc(SITE.get("author", ""))}</name>{site_email}</author>
{chr(10).join(entries)}
</feed>'''
    return xml


def render_sitemap(posts, pages, docs, notes=None):
    from urllib.parse import quote
    base = SITE.get("base", "").rstrip("/") + "/"
    today = datetime.date.today().isoformat()
    q = lambda u: base + quote(u, safe="/:?=&%")

    def url_entry(path, lastmod=None, freq="weekly", pri="0.8"):
        if lastmod is None:
            lm = today
        elif isinstance(lastmod, (datetime.date, datetime.datetime)):
            lm = lastmod.isoformat()
        else:
            lm = str(lastmod)
        return (f'  <url><loc>{q(path)}</loc><lastmod>{lm}</lastmod>'
                f'<changefreq>{freq}</changefreq><priority>{pri}</priority></url>')

    urls = [url_entry("", today, "daily", "1.0"),
            url_entry("archive/", freq="weekly", pri="0.8"),
            url_entry("tags/", freq="weekly", pri="0.6"),
            url_entry("search/", freq="monthly", pri="0.3")]
    if CONFIG.get("dynamic", {}).get("enabled"):
        urls.append(url_entry("dynamic/", freq="daily", pri="0.8"))
    if (CONFIG.get("notes") or {}).get("enabled"):
        urls.append(url_entry("notes/", freq="weekly", pri="0.8"))
    if (CONFIG.get("plugins") or {}).get("enabled"):
        urls.append(url_entry("plugins/", freq="monthly", pri="0.3"))
    if docs:
        urls.append(url_entry("docs/", freq="weekly", pri="0.9"))
    for pg in pages:
        urls.append(url_entry(pg["url"], freq="weekly", pri="0.7"))
    for d in docs:
        urls.append(url_entry(d["url"], d.get("date") or today, freq="monthly", pri="0.8"))
    for n in notes or []:
        urls.append(url_entry(n["url"], n.get("date") or today, freq="monthly", pri="0.6"))
    for p in posts:
        urls.append(url_entry(p["url"], p["date"], freq="monthly", pri="1.0"))
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>")


def render_search_index(posts, pages, docs=None, notes=None):
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
    for n in notes or []:
        data.append({
            "type": "note",
            "title": n["title"],
            "url": SITE.get("base", "").rstrip("/") + "/" + n["url"],
            "date": n["date_str"],
            "category": "笔记",
            "tags": n.get("tags") or [],
            "summary": n.get("summary") or n["content_text"][:160],
            "content": n["content_text"][:400],
        })
    return json.dumps(data, ensure_ascii=False, indent=1)


# --------------------------------------------------------------- 构建 ----

def minify_css(text):
    """轻量 CSS 压缩: 去注释、折叠空白、去掉冗余分隔符 (仅用于构建期产物)"""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([{}:;,>])\s*", r"\1", text)
    text = re.sub(r";}", "}", text)
    return text.strip()


def write(path, content, root=DIST):
    fp = root / path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")


def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    # 署名标准锁定: 配置被改动立即崩溃 (不可修改/篡改防线)
    assert_standard_sign()

    posts = load_posts()
    pages = load_pages()
    docs = load_docs()
    notes = load_notes()
    friends = CONFIG.get("friends") or []
    links = CONFIG.get("links") or {}
    forms = CONFIG.get("forms") or []
    link_submit = CONFIG.get("link_submit", "")
    global _ALL_POSTS
    _ALL_POSTS = posts

    # 首页 + 分页 (每页 posts_per_page 篇, 默认 10)
    per_page = int(SITE.get("posts_per_page", 10))
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

    # 笔记
    if (CONFIG.get("notes") or {}).get("enabled"):
        write("notes/index.html", render_notes_index(notes))
        for n in notes:
            write(f"notes/{n['slug']}/index.html", render_note(n, notes))

    # 动态 (朋友圈式时间线)
    if (CONFIG.get("dynamic") or {}).get("enabled"):
        write("dynamic/index.html", render_dynamic(posts, notes))

    # 插件注册表页 + 插件注册的额外静态页
    if (CONFIG.get("plugins") or {}).get("enabled"):
        write("plugins/index.html", render_plugins_index())
        for path, html in plugin_pages():
            write(path, html)

    # 友链 (+ 朋友圈 RSS 聚合, 失败安全降级)
    circle, c_ok, c_total = fetch_friend_circle(friends)
    write("links/index.html", render_links(friends, link_submit, circle=circle))

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
    write("sitemap.xml", render_sitemap(posts, pages, docs, notes))
    write("search_index.json", render_search_index(posts, pages, docs, notes))
    # robots: 放行抓取 + 声明 sitemap; 绝不排除 IndexNow key 文件
    base_url = SITE.get("base", "").rstrip("/") + "/"
    robots = ("User-agent: *\n"
              "Allow: /\n"
              "Disallow: /go/\n"
              "Sitemap: %ssitemap.xml\n" % base_url)
    write("robots.txt", robots)
    # 防止 GitHub Pages 的 Jekyll 干扰静态构建产物
    write(".nojekyll", "")
    # IndexNow 密钥文件: 配置 seo.indexnow_key 后构建即生成, 供 Bing/IndexNow 爬虫验证
    seo_cfg = CONFIG.get("seo") or {}
    ik = (seo_cfg.get("indexnow_key") or "").strip()
    if ik and re.fullmatch(r"[A-Za-z0-9_-]{6,64}", ik):
        write("%s.txt" % ik, ik)

    # 静态资源
    src_static = THEME / "static"
    if src_static.exists():
        shutil.copytree(src_static, DIST / "static")
        # 构建期压缩 CSS, 减小首屏阻塞传输量
        for css_fp in (DIST / "static" / "css").rglob("*.css"):
            css_fp.write_text(minify_css(css_fp.read_text(encoding="utf-8")), encoding="utf-8")

    # 署名完整性校验 (防移除防线): 缺少署名/令牌即构建崩溃
    verify_build_integrity()

    print(f"[OK] 共生成 {len(posts)} 篇文章, {len(pages)} 个页面, {len(docs)} 篇文档, {len(notes)} 篇笔记, "
          f"{len(friends)} 个友链, {len(forms)} 个表单, {len(links)} 条短链, 分页 {total_pages} 页")
    if c_total:
        print(f"[OK] 友链朋友圈: 抓取成功 {c_ok}/{c_total} 个 RSS 源")
    print(f"[OK] 插件: {len(load_plugins())} 个已加载")
    print(f"[OK] 站点输出目录: {DIST}")


if __name__ == "__main__":
    build()