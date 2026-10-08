/* ============================================================
 * OverCome 站点监测 (纯静态, 零依赖)
 * 1) 页面加载性能: 首字节 / DOM 就绪 / 完全加载
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

  // ---- 1) 页面性能 (Navigation Timing) ----
  if (window.performance && performance.timing) {
    var t = performance.timing;
    var ttfb = t.responseStart - t.navigationStart;
    var dom = t.domContentLoadedEventEnd - t.navigationStart;
    var loadT = t.loadEventEnd - t.navigationStart;
    var row = el('div', 'monitor-row perf');
    row.appendChild(el('b', '', '页面性能'));
    row.appendChild(el('span', '', '首字节 ' + fmt(ttfb) + ' · 就绪 ' + fmt(dom) + ' · 加载 ' + fmt(loadT)));
    box.appendChild(row);
  }

  // ---- 2) 目标探测 ----
  var targets = parseTargets();
  if (!targets.length) {
    box.appendChild(el('p', 'monitor-note', '未配置监测目标（config.monitor.targets）'));
    return;
  }
  box.appendChild(el('div', 'monitor-row', ''));
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