/* OverCome 站内全文搜索 */
(function () {
  'use strict';

  var input = document.getElementById('search-input');
  var btn = document.getElementById('search-btn');
  var hint = document.getElementById('search-hint');
  var results = document.getElementById('search-results');
  if (!input || !results) return;

  var indexData = null;

  function fetchIndex() {
    if (indexData) return Promise.resolve(indexData);
    return fetch('../search_index.json')
      .then(function (r) { return r.json(); })
      .then(function (data) { indexData = data; return data; });
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* 分词: 按空白/逗号/顿号/分号拆分, 过滤空词 */
  function tokenize(q) {
    return q.toLowerCase().split(/[\s,，、;；]+/).filter(Boolean);
  }

  function termRe(t) {
    return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function highlightText(text, terms) {
    var t = escapeHtml(text);
    terms.forEach(function (term) {
      if (!term) return;
      var re = new RegExp('(' + termRe(term) + ')', 'gi');
      t = t.replace(re, '<mark>$1</mark>');
    });
    return t;
  }

  /* 全部词都必须命中 (AND), 标题/标签/分类/摘要加权计分 */
  function score(item, terms) {
    var full = (item.title + ' ' + (item.summary || '') + ' ' + (item.category || '') + ' ' + (item.tags || []).join(' ') + ' ' + (item.content || '')).toLowerCase();
    var allHit = terms.every(function (t) { return full.indexOf(t) >= 0; });
    if (!allHit) return 0;
    var s = 0;
    var titleL = item.title.toLowerCase();
    terms.forEach(function (term) {
      if (titleL.indexOf(term) >= 0) s += 10;
      if ((item.tags || []).join(',').toLowerCase().indexOf(term) >= 0) s += 8;
      if ((item.category || '').toLowerCase().indexOf(term) >= 0) s += 6;
      if ((item.summary || '').toLowerCase().indexOf(term) >= 0) s += 3;
      s += 1;
    });
    return s;
  }

  function doSearch(query) {
    query = (query || '').trim();
    if (!query) {
      results.innerHTML = '';
      hint.textContent = '输入关键词即可全文检索本站内容';
      return;
    }
    var terms = tokenize(query);
    fetchIndex().then(function (data) {
      var hits = data
        .map(function (item) { return { item: item, s: score(item, terms) }; })
        .filter(function (x) { return x.s > 0; })
        .sort(function (a, b) { return b.s - a.s; })
        .slice(0, 20);

      hint.textContent = hits.length ? '找到 ' + hits.length + ' 条结果' : '没有找到相关内容，换个关键词试试';
      if (!hits.length) {
        results.innerHTML = '<li class="empty">暂无匹配结果</li>';
        return;
      }
      results.innerHTML = hits.map(function (x) {
        var it = x.item;
        var metaBits = [];
        if (it.date) metaBits.push(it.date);
        if (it.type === 'post') metaBits.push('分类: ' + it.category);
        if (it.tags && it.tags.length) metaBits.push('标签: ' + it.tags.join(', '));
        return '<li>' +
          '<a class="title" href="' + it.url + '">' + highlightText(it.title, terms) + '</a>' +
          '<div class="meta">' + metaBits.map(escapeHtml).join(' · ') + '</div>' +
          (it.summary ? '<p class="snippet">' + highlightText(it.summary.slice(0, 120), terms) + '</p>' : '') +
          '</li>';
      }).join('');
    }).catch(function () {
      results.innerHTML = '<li class="empty">搜索索引加载失败，请稍后重试。</li>';
    });
  }

  function run() { doSearch(input.value); }

  btn.addEventListener('click', run);
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter') run(); });
  input.addEventListener('input', function () {
    if (input.value.trim().length >= 2) run();
    else { results.innerHTML = ''; hint.textContent = '输入关键词即可全文检索本站内容'; }
  });
})();