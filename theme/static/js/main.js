/* OverCome 主脚本：主题切换、移动端侧栏、目录锚点、代码高亮、复制按钮 */
(function () {
  'use strict';

  /* ---------- 深色模式切换 ---------- */
  function giscusTheme(dark) {
    return dark ? 'dark' : 'light';
  }
  function syncGiscus(dark) {
    var frame = document.querySelector('iframe.giscus-frame');
    if (!frame || !frame.contentWindow) return;
    frame.contentWindow.postMessage({
      giscus: { setConfig: { theme: giscusTheme(dark) } }
    }, 'https://giscus.app');
  }
  function setupTheme() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var dark = document.documentElement.classList.toggle('dark');
      try { localStorage.setItem('overcome-theme', dark ? 'dark' : 'light'); } catch (e) { /* noop */ }
      syncGiscus(dark);
    });
  }

  /* ---------- 移动端侧栏 ---------- */
  function setupSidebar() {
    var menu = document.getElementById('menu-toggle');
    var sidebar = document.querySelector('.sidebar');
    if (!menu || !sidebar) return;
    var overlay = document.createElement('div');
    overlay.className = 'overlay';
    document.body.appendChild(overlay);

    function close() {
      sidebar.classList.remove('open');
      menu.classList.remove('open');
      overlay.classList.remove('show');
      menu.setAttribute('aria-expanded', 'false');
    }
    menu.addEventListener('click', function () {
      var isOpen = sidebar.classList.toggle('open');
      menu.classList.toggle('open', isOpen);
      overlay.classList.toggle('show', isOpen);
      menu.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
    overlay.addEventListener('click', close);
    sidebar.addEventListener('click', function (e) {
      if (e.target.closest('a')) close();
    });
  }

  /* ---------- 目录展示（仅当文章有目录时） ---------- */
  function setupToc() {
    var toc = document.querySelector('.toc');
    if (!toc || !toc.querySelector('.toc-links a')) return;
    toc.style.display = 'block';
  }

  /* ---------- 轻量代码高亮 ---------- */
  var KEYWORDS = {
    python: 'def|class|return|if|elif|else|for|while|import|from|as|try|except|finally|with|lambda|pass|break|continue|None|True|False|and|or|not|in|is|yield|global|nonlocal|raise|assert|async|await|del',
    javascript: 'function|return|var|let|const|if|else|for|while|do|switch|case|break|continue|new|typeof|instanceof|this|class|extends|super|import|export|from|default|try|catch|finally|throw|async|await|yield|null|undefined|true|false|of|in|delete|void',
    js: 'function|return|var|let|const|if|else|for|while|do|switch|case|break|continue|new|typeof|instanceof|this|class|extends|super|import|export|from|default|try|catch|finally|throw|async|await|yield|null|undefined|true|false|of|in|delete|void',
    typescript: 'interface|type|function|return|var|let|const|if|else|for|while|switch|case|break|continue|new|typeof|this|class|extends|implements|export|import|from|try|catch|finally|throw|async|await|null|undefined|true|false|of|in|readonly|enum|namespace|public|private|protected|static',
    ts: 'interface|type|function|return|var|let|const|if|else|for|while|switch|case|break|continue|new|typeof|this|class|extends|implements|export|import|from|try|catch|finally|throw|async|await|null|undefined|true|false|of|in|readonly|enum|namespace|public|private|protected|static',
    java: 'public|private|protected|class|interface|extends|implements|return|if|else|for|while|do|switch|case|break|continue|new|try|catch|finally|throw|throws|static|final|void|int|long|double|float|boolean|String|import|package|this|super|abstract|synchronized|instanceof|true|false|null',
    c: 'int|char|float|double|void|return|if|else|for|while|do|switch|case|break|continue|struct|typedef|enum|union|const|static|extern|sizeof|include|define|main|true|false|NULL',
    cpp: 'int|char|float|double|void|return|if|else|for|while|do|switch|case|break|continue|struct|typedef|enum|class|const|static|namespace|using|template|typename|public|private|protected|new|delete|this|virtual|override|true|false|nullptr|include',
    csharp: 'public|private|protected|internal|class|interface|struct|enum|return|if|else|for|foreach|while|do|switch|case|break|continue|new|try|catch|finally|throw|static|readonly|const|void|int|long|double|float|bool|string|var|using|namespace|this|base|async|await|true|false|null',
    go: 'func|return|if|else|for|range|switch|case|break|continue|var|const|type|struct|interface|package|import|map|chan|go|defer|select|fallthrough|len|cap|append|make|new|true|false|nil|string|int|float64|bool',
    rust: 'fn|let|mut|const|if|else|for|while|loop|match|return|struct|enum|trait|impl|mod|use|pub|self|super|crate|where|move|ref|match|break|continue|true|false|String|Vec|Option|Result|Some|None|Ok|Err|async|await|dyn|static',
    ruby: 'def|class|module|return|if|elsif|else|unless|for|while|until|do|end|begin|rescue|ensure|require|include|extend|attr_reader|attr_writer|attr_accessor|lambda|proc|new|self|true|false|nil|and|or|not|case|when',
    php: 'function|return|if|else|elseif|for|foreach|while|do|switch|case|break|continue|class|interface|extends|implements|public|private|protected|static|final|abstract|namespace|use|echo|print|require|include|new|try|catch|finally|throw|true|false|null|array|and|or|not|as',
    bash: 'if|then|else|elif|fi|for|while|do|done|case|esac|function|return|echo|exit|export|local|read|cd|ls|mkdir|rm|cp|mv|grep|sed|awk|curl|wget|git|sudo|chmod|chown|tar|unzip|cat|less|source|set|shift',
    shell: 'if|then|else|elif|fi|for|while|do|done|case|esac|function|return|echo|exit|export|local|read|cd|ls|mkdir|rm|cp|mv|grep|sed|awk|curl|wget|git|sudo|chmod|chown|tar|unzip|cat|less|source|set|shift',
    sql: 'SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|TABLE|ALTER|DROP|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|AND|OR|NOT|NULL|PRIMARY|KEY|FOREIGN|REFERENCES|INDEX|UNIQUE|AS|IN|BETWEEN|LIKE|VALUES|INTO|SET|DISTINCT|COUNT|SUM|AVG|MIN|MAX',
    yaml: 'true|false|null|yes|no|on|off',
    json: 'true|false|null',
    html: 'html|head|body|div|span|p|a|img|ul|ol|li|table|tr|td|th|form|input|button|script|style|link|meta|title|h1|h2|h3|h4|h5|h6|section|article|nav|header|footer|main|aside|blockquote|pre|code|em|strong|br|hr',
    css: 'margin|padding|border|background|color|font|display|position|width|height|top|left|right|bottom|flex|grid|gap|align|justify|content|size|family|weight|style|transform|transition|opacity|z-index|overflow|text|line|letter|box|shadow|radius|cursor|list|outline|float|clear|min|max|absolute|relative|fixed|sticky|block|inline|flex|grid|none|auto|inherit'
  };

  function extract(className) {
    var m = className.match(/lang-([\w-]+)/);
    return m ? m[1].toLowerCase() : '';
  }

  function highlight(code, lang) {
    if (!lang || !KEYWORDS[lang]) return code;
    var kwSet = {};
    KEYWORDS[lang].split('|').forEach(function (w) { kwSet[w.toLowerCase()] = true; });

    /* 顺序重要: 字符串优先于注释, 避免 // 或 # 在字符串内被误判 */
    var patterns = [
      { type: 'str', re: /("[^"\n]*"|'[^'\n]*'|`[^`]*`)/ },
      { type: 'com', re: /(\/\/[^\n]*|#.*$|<!--.*$|--[^\n]*|\/\*[\s\S]*?\*\/)/ },
      { type: 'num', re: /\b(\d+(\.\d+)?)\b/ }
    ];

    var lines = code.split('\n');
    var lineResults = [];
    for (var li = 0; li < lines.length; li++) {
      lineResults.push(tokenizeLine(lines[li], patterns, kwSet));
    }
    return lineResults.join('\n');
  }

  function tokenizeLine(line, patterns, kwSet) {
    var out = '';
    var i = 0;
    while (i < line.length) {
      var replaced = false;
      var rest = line.slice(i);
      for (var pi = 0; pi < patterns.length; pi++) {
        var p = patterns[pi];
        var mm = p.re.exec(rest);
        if (mm && mm.index === 0) {
          out += '<span class="' + p.type + '">' + escapeHtml(mm[0]) + '</span>';
          i += mm[0].length;
          replaced = true;
          break;
        }
      }
      if (replaced) continue;
      /* 读一个单词或字符 */
      var wm = /^[A-Za-z_][A-Za-z0-9_]*/.exec(line.slice(i));
      if (wm) {
        var word = wm[0];
        if (kwSet[word.toLowerCase()]) {
          out += '<span class="kw">' + word + '</span>';
        } else {
          out += escapeHtml(word);
        }
        i += word.length;
        continue;
      }
      out += escapeHtml(line[i]);
      i++;
    }
    return out;
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function setupHighlight() {
    var blocks = document.querySelectorAll('pre.code-block code[class*="lang-"]');
    blocks.forEach(function (el) {
      var lang = extract(el.className);
      var raw = el.textContent || el.innerText;
      lang = lang.replace(/[^a-z0-9]/g, '');
      if (KEYWORDS[lang] && raw) {
        el.innerHTML = highlight(raw, lang);
      }
    });

    /* 复制按钮 */
    document.querySelectorAll('.code-block').forEach(function (pre) {
      var btn = pre.querySelector('.code-copy');
      if (!btn) return;
      btn.addEventListener('click', function () {
        var code = pre.querySelector('code');
        var text = code.innerText || code.textContent;
        function done() { btn.textContent = '已复制'; setTimeout(function () { btn.textContent = '复制'; }, 1600); }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(done);
        } else {
          var ta = document.createElement('textarea');
          ta.value = text; document.body.appendChild(ta); ta.select();
          try { document.execCommand('copy'); } catch (e) { /* noop */ }
          document.body.removeChild(ta); done();
        }
      });
    });
  }

  /* ---------- 锚点平滑滚动 (保留标题点击) ---------- */
  function setupAnchors() {
    document.querySelectorAll('.toc a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var target = document.querySelector(a.getAttribute('href'));
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  /* ---------- 阅读进度条 + 回到顶部 ---------- */
  function setupReading() {
    var bar = document.getElementById('progress-bar');
    var topBtn = document.getElementById('back-to-top');
    var ticking = false;

    function update() {
      var scrollTop = window.scrollY || document.documentElement.scrollTop;
      var height = document.documentElement.scrollHeight - window.innerHeight;
      var pct = height > 0 ? (scrollTop / height) * 100 : 0;
      if (bar && bar.firstElementChild) bar.firstElementChild.style.width = pct + '%';
      if (topBtn) topBtn.classList.toggle('show', scrollTop > 480);
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
    }, { passive: true });
    window.addEventListener('resize', update);
    update();

    if (topBtn) {
      topBtn.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    setupTheme();
    setupSidebar();
    setupToc();
    setupHighlight();
    setupAnchors();
    setupReading();
  });
})();