/* OverCome 媒体查看器 + 链接策略
 * 1) 正文(.post-body)内图片 -> 灯箱(缩放/拖动/方向键切换/单击关闭)
 * 2) 正文内视频/PDF/Office 文档 -> 灯箱在线查看(原生控件提供进度与缩放)
 * 3) 链接跳转策略: config.link_strategy -> meta[name=overcome-links]
 *    站内 self 当前页 / 站外 blank 新标签 (均可配置, 且正文链接不再被写死 target)
 * 4) 关闭路径: 右上角 ✕ / Esc / 点击边缘 / 单击灯箱内内容(区分双击缩放与拖动)
 */
(function () {
  'use strict';

  var ORIGIN = location.origin;
  var overlay, stage, content, caption, toolbar, closeBtn;
  var state = null; // {kind, list, index, scale, tx, ty, dragging...}

  /* 链接策略: 读取页面 meta, 缺失时默认站内当前页/站外新标签 */
  var LS = { internal: 'self', external: 'blank' };
  (function () {
    var m = document.querySelector('meta[name="overcome-links"]');
    if (!m) return;
    try {
      var o = JSON.parse(m.getAttribute('content') || '{}');
      if (o.internal === 'blank' || o.internal === 'self') LS.internal = o.internal;
      if (o.external === 'blank' || o.external === 'self') LS.external = o.external;
    } catch (e) { /* 保持默认 */ }
  })();

  function isSameOrigin(url) {
    if (!url) return true;
    if (/^(mailto:|tel:|javascript:|#)/i.test(url)) return true;
    try {
      return new URL(url, location.href).origin === ORIGIN;
    } catch (e) {
      return true;
    }
  }

  function isExternal(url) {
    return /^(https?:)?\/\//i.test(url) && !isSameOrigin(url);
  }

  /* 打开链接: 尊重用户操作, 新标签统一加 rel */
  function openBlank(href) {
    var w = window.open(href, '_blank');
    if (w) {
      try { w.opener = null; } catch (e) { /* noop */ }
    }
  }

  /* ---------- 链接跳转策略 (全局, 覆盖正文/侧栏/卡片生成的所有链接) ---------- */
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (/^(mailto:|tel:|javascript:)/i.test(href)) return;
    if (a.hasAttribute('target')) return; // 显式指定的 target 尊重 (如友链/社交/嵌入卡片的新窗口)
    if (/^#/.test(href)) return;
    var ext = isExternal(href);
    if (ext && LS.external === 'blank') {
      e.preventDefault();
      openBlank(href);
    } else if (!ext && LS.internal === 'blank') {
      e.preventDefault();
      openBlank(href);
    }
    // 其余情况: 默认行为 (站内当前页跳转 / 站外 self)
  });

  /* ---------- 灯箱 ---------- */
  function ensureOverlay() {
    if (overlay) return;
    overlay = document.createElement('div');
    overlay.className = 'viewer-overlay';
    overlay.innerHTML =
      '<button class="viewer-btn viewer-close" type="button" aria-label="关闭查看器" title="关闭 (Esc / 点击内容)">✕</button>' +
      '<div class="viewer-stage">' +
      '  <div class="viewer-content"></div>' +
      '  <div class="viewer-toolbar" hidden>' +
      '    <button class="viewer-btn" data-act="prev" type="button" title="上一项 (←)">‹ 上一项</button>' +
      '    <button class="viewer-btn" data-act="zoom-out" type="button" title="缩小">−</button>' +
      '    <span class="viewer-zoom-info">100%</span>' +
      '    <button class="viewer-btn" data-act="zoom-in" type="button" title="放大">＋</button>' +
      '    <button class="viewer-btn" data-act="reset" type="button" title="复位 (双击)">复位</button>' +
      '    <button class="viewer-btn" data-act="next" type="button" title="下一项 (→)">下一项 ›</button>' +
      '    <span class="viewer-meta"></span>' +
      '  </div>' +
      '</div>';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (ev) {
      if (ev.target === overlay || ev.target === stage) closeViewer();
    });
    toolbar = overlay.querySelector('.viewer-toolbar');
    content = overlay.querySelector('.viewer-content');
    caption = document.createElement('div');
    caption.className = 'viewer-caption';
    overlay.querySelector('.viewer-stage').appendChild(caption);
    closeBtn = overlay.querySelector('.viewer-close');
    closeBtn.addEventListener('click', function (ev) {
      ev.stopPropagation();
      closeViewer();
    });
    toolbar.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-act]');
      if (!btn) return;
      onToolbar(btn.getAttribute('data-act'));
    });
    overlay.addEventListener('wheel', function (ev) {
      if (!state || state.kind !== 'image') return;
      ev.preventDefault();
      var d = ev.deltaY > 0 ? -1 : 1;
      setScale(state.scale * (d > 0 ? 1.18 : 1 / 1.18));
    }, { passive: false });
    document.addEventListener('keydown', function (ev) {
      if (!state) return;
      if (ev.key === 'Escape') closeViewer();
      else if (state.kind === 'image') {
        if (ev.key === 'ArrowLeft') showIndex(state.index - 1);
        else if (ev.key === 'ArrowRight') showIndex(state.index + 1);
      }
    });
    makeDraggable();
  }

  function onToolbar(act) {
    if (!state) return;
    if (act === 'prev') showIndex(state.index - 1);
    else if (act === 'next') showIndex(state.index + 1);
    else if (act === 'zoom-in') setScale(state.scale * 1.25);
    else if (act === 'zoom-out') setScale(state.scale / 1.25);
    else if (act === 'reset') setScale(1);
  }

  function setScale(s) {
    if (!state || state.kind !== 'image') return;
    state.scale = Math.min(8, Math.max(0.2, s));
    applyImageTransform();
  }

  function applyImageTransform() {
    var img = content.querySelector('img');
    if (!img) return;
    img.style.transform = 'translate(' + state.tx + 'px,' + state.ty + 'px) scale(' + state.scale + ')';
    var zinfo = toolbar.querySelector('.viewer-zoom-info');
    if (zinfo) zinfo.textContent = Math.round(state.scale * 100) + '%';
  }

  /* 单击关闭: 与拖动/双击缩放区分 (moved 阈值 6px, 双击窗口 280ms) */
  var clickTimer = null;

  function cancelClickClose() {
    if (clickTimer) { clearTimeout(clickTimer); clickTimer = null; }
  }

  function scheduleClickClose() {
    if (clickTimer) { cancelClickClose(); return; } // 第二次点击: 构成双击, 交给 dblclick 缩放
    clickTimer = setTimeout(function () {
      clickTimer = null;
      if (state) closeViewer();
    }, 280);
  }

  function makeDraggable() {
    var dragging = null;
    document.addEventListener('mousedown', function (ev) {
      var img = ev.target;
      if (!img || !img.closest || !img.closest('.viewer-content')) return;
      if (!img.matches('img')) return;
      if (state) state.dragging = true;
      img.classList.add('viewer-dragging');
      dragging = { x: ev.clientX, y: ev.clientY, tx: state ? state.tx : 0, ty: state ? state.ty : 0, moved: false };
    });
    document.addEventListener('mousemove', function (ev) {
      if (!dragging || !state) return;
      if (Math.abs(ev.clientX - dragging.x) > 6 || Math.abs(ev.clientY - dragging.y) > 6) dragging.moved = true;
      state.tx = dragging.tx + (ev.clientX - dragging.x);
      state.ty = dragging.ty + (ev.clientY - dragging.y);
      applyImageTransform();
    });
    document.addEventListener('mouseup', function (ev) {
      var wasDrag = dragging ? dragging.moved : false;
      if (dragging) dragging = null;
      if (state) {
        state.dragging = false;
        var img = content.querySelector('img');
        if (img) img.classList.remove('viewer-dragging');
      }
      /* 单击(未拖动)灯箱内内容 -> 关闭; 图片在 mousedown/mouseup 位移小才算单击。
         图片单击即关; 视频/文档等带原生控件的媒体, 仅点 content 空白区(边距/标题条)关闭,
         避免点播放/暂停按钮误关灯箱 */
      if (state && !wasDrag && ev.target && ev.target.closest && ev.target.closest('.viewer-content')) {
        if (state.kind === 'image') {
          scheduleClickClose();
        } else if (ev.target === content) {
          scheduleClickClose();
        }
      }
    });
    document.addEventListener('dblclick', function (ev) {
      if (!state || state.kind !== 'image') return;
      if (ev.target && ev.target.matches && ev.target.matches('.viewer-content img')) {
        cancelClickClose();
        setScale(state.scale === 1 ? 2 : 1);
      }
    }, true);
  }

  function showIndex(i) {
    if (!state || i < 0 || i >= state.list.length) return;
    state.index = i;
    setCaption(state.list[i]);
    var meta = toolbar.querySelector('.viewer-meta');
    if (meta) meta.textContent = (i + 1) + ' / ' + state.list.length;
    if (state.kind === 'image') renderImage();
    else renderMedia();
  }

  function renderImage() {
    var img = state.list[state.index];
    state.scale = 1; state.tx = 0; state.ty = 0;
    content.innerHTML = '<img src="' + img.src + '" alt="' + (img.alt || '') + '">';
    var el = content.querySelector('img');
    el.addEventListener('load', function () { applyImageTransform(); });
    applyImageTransform();
  }

  function renderMedia() {
    var url = state.list[state.index];
    content.innerHTML = '';
    if (state.kind === 'video') {
      var v = document.createElement('video');
      v.src = url;
      v.controls = true;
      v.autoplay = true;
      v.preload = 'metadata';
      content.appendChild(v);
    } else if (state.kind === 'pdf') {
      var f = document.createElement('iframe');
      f.src = url;
      f.setAttribute('title', '在线文档预览');
      content.appendChild(f);
      state.scale = 1;
    } else { // office 文档借助浏览器原生/Google Docs 预览
      var g = document.createElement('iframe');
      g.src = 'https://docs.google.com/viewer?url=' + encodeURIComponent(url) + '&embedded=true';
      g.setAttribute('title', '在线文档预览');
      content.appendChild(g);
    }
    setCaption(url);
  }

  function openViewer(kind, list, index) {
    ensureOverlay();
    state = { kind: kind, list: list, index: index || 0, scale: 1, tx: 0, ty: 0 };
    toolbar.hidden = kind !== 'image';
    document.body.classList.add('viewer-open');
    showIndex(state.index);
  }

  function closeViewer() {
    if (!state) return;
    state = null;
    cancelClickClose();
    if (content) content.innerHTML = '';
    if (caption) caption.textContent = '';
    document.body.classList.remove('viewer-open');
  }

  /* ---------- 文件名/alt 底部命名条 ---------- */
  function fileNameOf(url) {
    if (!url) return '';
    var clean = String(url).split('?')[0].split('#')[0];
    var segs = clean.split(/[\\/]/).filter(Boolean);
    var name = segs.pop() || '';
    try {
      name = decodeURIComponent(name);
    } catch (e) { /* 保留原样 */ }
    return name.trim();
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function setCaption(item) {
    if (!caption) return;
    var src = (typeof item === 'string') ? item : (item && item.src);
    var alt = (item && typeof item === 'object' && item.alt) ? String(item.alt).trim() : '';
    var name = fileNameOf(src);
    var parts = [];
    if (name) parts.push('<span class="vf-file">' + escapeHtml(name) + '</span>');
    if (alt && alt.toLowerCase() !== name.toLowerCase()) {
      parts.push('<span class="vf-alt">' + escapeHtml(alt) + '</span>');
    }
    caption.innerHTML = parts.join('');
  }

  /* ---------- 唤醒: 点击正文内图片/媒体 ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var body = t.closest('.post-body, .post-content, .page-body');
    if (!body) return;

    // 图片
    var img = t.closest('img[src]');
    if (img && !img.closest('a')) {
      e.preventDefault();
      var imgs = Array.prototype.slice.call(body.querySelectorAll('img[src]')).filter(function (x) {
        return !x.closest('a');
      });
      var idx = imgs.indexOf(img);
      openViewer('image', imgs.map(function (x) { return { src: x.getAttribute('src'), alt: x.getAttribute('alt') || '' }; }), idx);
      return;
    }

    // 媒体链接: 视频 / PDF / Office 文档
    var a = t.closest('a[href]');
    if (a) {
      var href = a.getAttribute('href') || '';
      var m = href.match(/\.(pdf|doc|docx|ppt|pptx|xls|xlsx|mp4|webm|mov|m4v)(\?.*)?$/i);
      if (m) {
        e.preventDefault();
        var ext = m[1].toLowerCase();
        var k = (ext === 'pdf') ? 'pdf' : ((ext === 'mp4' || ext === 'webm' || ext === 'mov' || ext === 'm4v') ? 'video' : 'office');
        if (k === 'video' || k === 'pdf') {
          openViewer(k, [href], 0);
        } else {
          openViewer('office', [href], 0);
        }
      }
    }
  });
})();