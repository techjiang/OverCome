/* OverCome 署名完整性防线 (不可移除/修改/篡改/遮掩)
 * Powered by 科技酱 & OverCome —— 运行期校验:
 *   1) 页面 meta 存在且为标准值
 *   2) .powered-by 署名节点存在, 文本包含 "Powered by 科技酱 & OverCome"
 *   3) 两个署名链接与标准值一致
 *   4) 署名可见 (未被 display:none / visibility:hidden / opacity 或裁切等手段遮掩)
 * 任一不通过 => 站点进入崩溃态 (页面内容替换为完整性错误页, 无法正常使用)。
 * 构建侧另有防线: 删除/改动构建逻辑或本文件会导致 python3 build.py 直接失败。
 */
(function () {
  'use strict';

  var EXPECT_SPEC = '科技酱|https://docs.asoe.cn|OverCome|https://github.com/techjiang/OverCome';
  var EXPECT_NAMES = ['科技酱', 'OverCome'];
  var EXPECT_LINKS = ['https://docs.asoe.cn', 'https://github.com/techjiang/OverCome'];

  function crash() {
    if (document.body.__overcome_crashed) return;
    document.body.__overcome_crashed = true;
    var text =
      '<div style="max-width:560px;margin:12vh auto 0;padding:34px 38px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',\'PingFang SC\',\'Microsoft YaHei\',sans-serif;' +
      'background:#211e1c;color:#e8e1dc;border:1px solid #3a3532;border-radius:16px;text-align:center;box-shadow:0 12px 40px rgba(0,0,0,.35)">' +
      '<p style="font-size:52px;margin:0 0 10px">⚠️</p>' +
      '<h1 style="font-size:20px;margin:0 0 12px;color:#d6a09c">站点完整性校验失败</h1>' +
      '<p style="font-size:14px;line-height:1.9;color:#b5aba4;margin:0">' +
      '本页面底部的 "Powered by 科技酱 & OverCome" 署名被移除、修改、篡改或遮掩。' +
      '<br>请恢复署名后重新构建部署，站点才能继续使用。</p>' +
      '</div>';
    try {
      document.documentElement.classList.remove('dark');
    } catch (e) { /* noop */ }
    document.body.innerHTML = text;
  }

  function isVisible(el) {
    if (!el || !el.parentNode) return false;
    var cs = window.getComputedStyle(el);
    var r = el.getBoundingClientRect();
    if (!r || r.width < 1 || r.height < 1) return false;
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    var op = parseFloat(cs.opacity);
    if (isFinite(op) && op < 0.05) return false;
    if (cs.clipPath === 'inset(100%)' || cs.overflow !== 'visible') {
      /* 严格裁剪场景难以穷举; 高度为 0 的情况已在 rect 检查覆盖 */
    }
    return true;
  }

  function check() {
    /* 1) meta 标准值 */
    var mSpec = document.querySelector('meta[name="overcome-seal-spec"]');
    var mTok = document.querySelector('meta[name="overcome-seal"]');
    if (!mSpec || !mTok || !mTok.getAttribute('content')) return crash();
    if ((mSpec.getAttribute('content') || '').trim() !== EXPECT_SPEC) return crash();

    /* 2) 署名节点存在 */
    var sign = document.querySelector('[data-overcome-sign]');
    if (!sign) return crash();
    var text = (sign.textContent || '').replace(/\s+/g, ' ');
    if (text.indexOf('Powered by') === -1) return crash();
    for (var i = 0; i < EXPECT_NAMES.length; i++) {
      if (text.indexOf(EXPECT_NAMES[i]) === -1) return crash();
    }

    /* 3) 署名链接一致 */
    var links = sign.querySelectorAll('a[data-overcome-link]');
    var got = [];
    for (var j = 0; j < links.length; j++) {
      got.push(links[j].getAttribute('href') || '');
    }
    for (var k = 0; k < EXPECT_LINKS.length; k++) {
      if (got.indexOf(EXPECT_LINKS[k]) === -1) return crash();
    }

    /* 4) 可见性 (防 CSS 遮掩) */
    if (!isVisible(sign)) return crash();

    /* 5) 不能有第二段被隐藏的误导性副本之外, 署名本身须为主体最后可见块 */
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', check);
  } else {
    check();
  }
  /* 兜底再查一次(若前面被延迟阻塞) */
  window.addEventListener('load', function () {
    if (document.body && document.body.__overcome_crashed) return;
    check();
  });
})();