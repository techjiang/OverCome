/* ============================================================
 * OverCome 站点监测 (纯静态, 零依赖)
 * 1) 页面加载性能: 首字节 / DOM 就绪 / 完全加载
 *    - 优先 PerformanceNavigationTiming (现代 API, 数值真实)
 *    - 就绪/加载指标在 DOMContentLoaded / load 事件触发后回填, 不再显示 "--"
 * 2) 目标站点状态: 延迟探测 + 在线/离线判定 (可配置 targets, 可手动重测)
 * 与左侧栏底部的不蒜子统计相互独立, 由 config.monitor 控制开关。
 * ============================================================ */
(function () {
  'use strict';
  var box = document.getElementById('monitor-box');
  if (!box) return;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function fmt(ms) {
    if (!isFinite(ms) || ms < 0) return '—';
    return ms >= 1000 ? (ms / 1000).toFixed(2) + ' s' : Math.round(ms) + ' ms';
  }
  function parseTargets() {
    try { return JSON.parse(box.getAttribute('data-targets') || '[]'); }
    catch (e) { return []; }
  }

  /* ---- 1) 页面性能 (Navigation Timing Level 2, 优先; 回退 level 1) ---- */
  var nav = null;
  try {
    var entries = window.performance && performance.getEntriesByType
      ? performance.getEntriesByType('navigation')
      : [];
    nav = entries && entries[0] ? entries[0] : null;
  } catch (e) { nav = null; }

  var t1 = (window.performance && performance.timing) ? performance.timing : null;

  function navVal(key) {
    if (nav && isFinite(nav[key]) && nav[key] > 0) return nav[key];
    if (t1) {
      var start = t1.navigationStart || 0;
      if (key === 'responseStart' && t1.responseStart) return t1.responseStart - start;
      if (key === 'domContentLoadedEventEnd' && t1.domContentLoadedEventEnd) return t1.domContentLoadedEventEnd - start;
      if (key === 'loadEventEnd' && t1.loadEventEnd) return t1.loadEventEnd - start;
    }
    return -1;
  }

  var perfRow = el('div', 'monitor-row perf');
  perfRow.appendChild(el('b', '', '页面性能'));
  var perfVal = el('span', '', '');
  perfRow.appendChild(perfVal);
  box.appendChild(perfRow);

  function renderPerf(force) {
    var b = navVal('responseStart');
    var d = navVal('domContentLoadedEventEnd');
    var l = navVal('loadEventEnd');
    var dTxt = d >= 0 ? fmt(d) : '等待就绪…';
    var lTxt = l >= 0 ? fmt(l) : '加载中…';
    perfVal.textContent = '首字节 ' + fmt(b) + ' · 就绪 ' + dTxt + ' · 加载 ' + lTxt;
    if (d >= 0 && l >= 0) {
      perfVal.setAttribute('data-done', '1');
    }
  }
  renderPerf();
  /* DOMContentLoaded 与 load 触发后回填真实指标 (解决"就绪/加载 一直 '—'"的问题)
     loadEventEnd / domContentLoadedEventEnd 在事件**结束后**才写入 PerformanceTiming,
     因此监听器内需延迟一拍(短 setTimeout)再读取, 否则仍读到 0。 */
  function later(fn) {
    setTimeout(fn, 120);
  }
  if (document.readyState === 'complete') {
    later(function () { renderPerf(true); });
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      later(function () { renderPerf(true); });
    }, { once: true });
    window.addEventListener('load', function () {
      later(function () { renderPerf(true); });
    }, { once: true });
  }

  /* ---- 2) 目标探测 ---- */
  var targets = parseTargets();
  if (!targets.length) {
    box.appendChild(el('p', 'monitor-note', '未配置监测目标（config.monitor.targets）'));
    return;
  }
  box.appendChild(el('div', 'monitor-row'));
  var rowT = box.lastChild;
  rowT.appendChild(el('b', '', '目标状态'));
  var list = el('div', 'monitor-targets');
  box.appendChild(list);
  var reBtn = el('button', 'monitor-refresh', '重新检测');
  reBtn.type = 'button';
  box.appendChild(reBtn);

  function probe(target) {
    var item = el('div', 'monitor-item checking');
    item.appendChild(el('span', 't-name', target.name || target.url));
    var st = el('span', 't-status', '检测中…');
    item.appendChild(st);
    list.appendChild(item);
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, 8000);
    var start = performance.now();
    fetch(target.url, { method: 'HEAD', mode: 'no-cors', cache: 'no-store', signal: ctrl.signal })
      .then(function () {
        clearTimeout(timer);
        var ms = performance.now() - start;
        st.textContent = fmt(ms) + ' · 在线';
        st.className = 't-status ok';
        item.className = 'monitor-item ok';
      })
      .catch(function () {
        clearTimeout(timer);
        var ms = performance.now() - start;
        st.textContent = (ms >= 8000 ? '超时 ' : '不可达 ') + fmt(ms);
        st.className = 't-status down';
        item.className = 'monitor-item down';
      });
  }
  function run() {
    list.innerHTML = '';
    targets.forEach(probe);
  }
  reBtn.addEventListener('click', run);
  run();
})();