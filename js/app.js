/* ==========================================================================
   中国现当代文学时间轴 · 引擎
   纯静态：数据来自 data/events.js（window.LIT_DATA），双击 index.html 即可运行
   ========================================================================== */
(function () {
  'use strict';

  var D = window.LIT_DATA;
  if (!D || !D.events || !D.events.length) {
    document.body.innerHTML =
      '<div style="padding:60px;text-align:center;font-family:sans-serif;color:#666">' +
      '数据未加载：请确认 <code>data/events.js</code> 存在且格式正确。</div>';
    return;
  }

  /* ---------------- 常量与工具 ---------------- */
  var LANE_ROW = 22;
  var MIN_PPU = 1.2;
  var MAX_PPU = 420;

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function store(key, val) {
    try {
      if (arguments.length === 1) { var v = localStorage.getItem(key); return v ? JSON.parse(v) : null; }
      localStorage.setItem(key, JSON.stringify(val));
    } catch (e) { /* 隐私模式忽略 */ }
  }
  function yearOf(dateStr) {
    var p = String(dateStr).split('-').map(Number);
    var y = p[0] || 0;
    if (!p[1]) return y + 0.5;            // 只有年份 → 落在年中
    return y + (p[1] - 0.5) / 12;         // 有月份 → 落在月中
  }
  function fmtDate(s) {
    var p = String(s).split('-');
    return [p[0], p[1], p[2]].filter(Boolean).join('.');
  }
  function yearLabel(s) {
    var p = String(s).split('-');
    return p[0] + (p[1] ? '.' + p[1] : '');
  }

  /* 量文字宽度（用于防重叠） */
  var mctx = document.createElement('canvas').getContext('2d');
  function textW(s, bold) {
    mctx.font = (bold ? '600 ' : '400 ') + '13px -apple-system,"PingFang SC","Hiragino Sans GB",sans-serif';
    return mctx.measureText(s).width;
  }

  /* ---------------- 数据整形 ---------------- */
  var periods = (D.periods || []).slice().sort(function (a, b) { return a.start - b.start; });
  var lanes = (D.lanes || []).slice();
  var laneIndex = {};
  lanes.forEach(function (l, i) { laneIndex[l.id] = { def: l, order: i }; });

  function periodOf(year) {
    for (var i = 0; i < periods.length; i++) {
      if (year >= periods[i].start && year < periods[i].end) return periods[i].id;
    }
    return periods.length ? periods[periods.length - 1].id : '';
  }

  var events = D.events.map(function (e, i) {
    var year = yearOf(e.date);
    var lane = laneIndex[e.lane] ? e.lane : 'event';
    return {
      raw: e,
      id: e.id || ('ev' + i + '-' + e.date),
      date: e.date,
      year: year,
      yLabel: yearLabel(e.date),
      title: e.title || '(无题)',
      lane: lane,
      kind: e.kind || '',
      importance: clamp(Number(e.importance) || 2, 1, 3),
      people: e.people || [],
      schools: e.schools || [],
      summary: e.summary || '',
      detail: e.detail || '',
      memory: e.memory || '',
      confuse: e.confuse || '',
      tags: e.tags || [],
      period: e.period && periods.some(function (p) { return p.id === e.period; }) ? e.period : periodOf(year)
    };
  }).sort(function (a, b) { return a.year - b.year || a.id.localeCompare(b.id); });

  var byId = {};
  events.forEach(function (e) { byId[e.id] = e; });

  var minYear = D.meta && D.meta.minYear ? D.meta.minYear : Math.min.apply(null, events.map(function (e) { return Math.floor(e.year); })) - 1;
  var maxYear = D.meta && D.meta.maxYear ? D.meta.maxYear : Math.ceil(Math.max.apply(null, events.map(function (e) { return e.year; }))) + 1;

  /* ---------------- 状态 ---------------- */
  var S = {
    periods: {}, lanes: {}, tags: {},
    q: '',
    view: { start: minYear, ppu: 40 },
    sel: null,
    mast: store('lit.mast') || {},
    quiz: null,
    listSig: '',
    fitted: false
  };

  /* ---------------- DOM 引用 ---------------- */
  var stage = $('#stage');
  var axisRow = $('#axis');
  var periodRow = $('#period');
  var lanesEl = $('#lanes');
  var tlEl = $('#tl');
  var mobEl = $('#mob');
  var drawer = $('#drawer');
  var statEl = $('#stat');
  var searchInput = $('#q');
  var searchBox = $('#search');

  /* ---------------- 视图换算 ---------------- */
  function gutter() {
    return parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--gutter')) || 96;
  }
  function viewW() { return Math.max(240, lanesEl.clientWidth || stage.clientWidth || 900); }
  function xOf(year) { return gutter() + (year - S.view.start) * S.view.ppu; }
  function yearAt(px) { return S.view.start + (px - gutter()) / S.view.ppu; }

  function fitPpu() {
    var w = viewW() - gutter() - 150;   // 右侧留出标签宽度
    return clamp(w / Math.max(1, maxYear - minYear), MIN_PPU, MAX_PPU);
  }
  function clampView() {
    var w = viewW() - gutter();
    var ppu = clamp(S.view.ppu, Math.min(MIN_PPU, fitPpu() * 0.8), MAX_PPU);
    var span = w / ppu;
    var lo = minYear - span * 0.35;
    var hi = maxYear - span * 0.65;
    if (hi < lo) { lo = minYear; hi = maxYear; }
    return { ppu: ppu, start: clamp(S.view.start, Math.min(lo, hi), Math.max(lo, hi)) };
  }

  function fit() {
    S.view.ppu = fitPpu();
    S.view.start = minYear - 14 / S.view.ppu;
    S.view = clampView();
    render();
  }
  function zoomAt(factor, px) {
    var y = yearAt(px == null ? viewW() / 2 : px);
    S.view.ppu = clamp(S.view.ppu * factor, fitPpu() * 0.8, MAX_PPU);
    S.view.start = y - ((px == null ? viewW() / 2 : px) - gutter()) / S.view.ppu;
    S.view = clampView();
    render();
  }
  function panBy(dYears) { S.view.start += dYears; S.view = clampView(); render(); }
  function centerOn(year) {
    S.view.start = year - (viewW() - gutter()) / 2 / S.view.ppu;
    S.view = clampView();
    render();
  }

  /* ---------------- 筛选 ---------------- */
  function pass(e) {
    var ps = Object.keys(S.periods), ls = Object.keys(S.lanes), ts = Object.keys(S.tags);
    if (ps.length && !S.periods[e.period]) return false;
    if (ls.length && !S.lanes[e.lane]) return false;
    if (ts.length) {
      var okTag = e.tags.some(function (t) { return S.tags[t]; });
      if (!okTag) return false;
    }
    return true;
  }
  function matched(e) {
    if (!S.q) return true;
    var k = S.q.toLowerCase();
    var hay = [e.title, e.kind, e.summary, e.detail, e.memory, e.confuse, e.yLabel, e.raw.chapter || '']
      .concat(e.people, e.schools, e.tags).join(' ').toLowerCase();
    return hay.indexOf(k) >= 0;
  }
  function visible() { return events.filter(pass); }

  /* ---------------- 芯片 ---------------- */
  var CHIP_KEY = { period: 'periods', lane: 'lanes', tag: 'tags' };
  function buildChips() {
    var pBox = $('#chips-period'), lBox = $('#chips-lane'), tBox = $('#chips-tag');
    periods.forEach(function (p) {
      pBox.appendChild(chip(p.name, p.color, 'period', p.id));
    });
    lanes.forEach(function (l) {
      lBox.appendChild(chip(l.name, l.color, 'lane', l.id));
    });
    /* 标签按钮按数据里实际出现的标签生成，避免出现永远筛不出结果的死按钮 */
    var tagCount = {};
    events.forEach(function (e) {
      e.tags.forEach(function (t) { tagCount[t] = (tagCount[t] || 0) + 1; });
    });
    var tagOrder = ['必背', '常考', '真题', '名词解释', '简答', '高频', '作品', '思潮', '社团刊物'];
    var tags = Object.keys(tagCount).sort(function (a, b) {
      var ia = tagOrder.indexOf(a), ib = tagOrder.indexOf(b);
      if (ia < 0) ia = 99;
      if (ib < 0) ib = 99;
      if (ia !== ib) return ia - ib;
      return tagCount[b] - tagCount[a];
    });
    tags.forEach(function (t) {
      if (tagCount[t] >= 3) tBox.appendChild(chip(t, null, 'tag', t));
    });
  }
  function chip(label, color, group, id) {
    var b = document.createElement('button');
    b.className = 'chip';
    b.dataset.group = group;
    b.dataset.id = id;
    b.type = 'button';
    b.innerHTML = (color ? '<i class="swatch" style="background:' + color + '"></i>' : '') + esc(label);
    b.addEventListener('click', function () {
      var set = S[CHIP_KEY[group]];
      if (set[id]) delete set[id]; else set[id] = true;
      b.classList.toggle('on', !!set[id]);
      render();
    });
    return b;
  }

  /* ---------------- 渲染：坐标轴 ---------------- */
  function renderAxis() {
    var w = viewW();
    var html = '<div class="axis-gutter">年代</div>';
    var steps = [1, 2, 5, 10, 20, 50, 100];
    var step = steps[steps.length - 1];
    for (var i = 0; i < steps.length; i++) {
      if (steps[i] * S.view.ppu >= 62) { step = steps[i]; break; }
    }
    var y0 = Math.floor(yearAt(0) / step) * step;
    var y1 = yearAt(w) + step;
    for (var y = y0; y <= y1; y += step) {
      var x = xOf(y);
      if (x < gutter() - 2 || x > w + 60) continue;
      var major = y % 10 === 0;
      html += '<div class="tick' + (major ? ' major' : '') + '" style="left:' + x.toFixed(1) + 'px"></div>';
      html += '<div class="tick-label' + (major ? ' major' : '') + '" style="left:' + x.toFixed(1) + 'px">' + y + '</div>';
    }
    /* 半格刻度 */
    if (step >= 5) {
      for (var y2 = Math.floor(yearAt(0) / (step / 2)) * (step / 2); y2 <= y1; y2 += step / 2) {
        if (y2 % step === 0) continue;
        var x2 = xOf(y2);
        if (x2 < gutter() - 2 || x2 > w + 60) continue;
        if ((step / 2) * S.view.ppu < 16) continue;
        html += '<div class="tick" style="left:' + x2.toFixed(1) + 'px;height:4px"></div>';
      }
    }
    /* 今天 */
    var nowY = new Date().getFullYear() + 0.5;
    if (nowY > S.view.start) {
      var xn = xOf(nowY);
      if (xn > gutter() && xn < w) {
        html += '<div class="tick major" style="left:' + xn.toFixed(1) + 'px;height:14px;background:#c92820;opacity:.5"></div>';
        html += '<div class="tick-label" style="left:' + xn.toFixed(1) + 'px;color:#c92820">今</div>';
      }
    }
    axisRow.innerHTML = html;
  }

  /* ---------------- 渲染：时期条 ---------------- */
  function renderPeriods() {
    var w = viewW();
    var html = '';
    periods.forEach(function (p) {
      var x1 = xOf(p.start), x2 = xOf(p.end);
      if (x2 < gutter() || x1 > w) return;
      var wid = Math.max(0, x2 - x1);
      html += '<div class="period-seg' + (S.periods[p.id] ? ' on' : '') + '" data-pid="' + p.id + '" ' +
        'style="left:' + Math.max(x1, gutter()).toFixed(1) + 'px;width:' + (wid - 1).toFixed(1) + 'px">' +
        (wid > 46 ? '<span>' + esc(p.name) + '</span>' : '') + '</div>';
    });
    periodRow.innerHTML = html;
    $$('.period-seg', periodRow).forEach(function (seg) {
      seg.addEventListener('click', function () {
        var p = periods.filter(function (x) { return x.id === seg.dataset.pid; })[0];
        if (!p) return;
        var pad = (p.end - p.start) * 0.08;
        var w2 = viewW() - gutter();
        S.view.ppu = clamp(w2 / (p.end - p.start + pad * 2), fitPpu() * 0.8, MAX_PPU);
        S.view.start = p.start - pad;
        S.view = clampView();
        render();
      });
    });
  }

  /* ---------------- 渲染：轨道 ---------------- */
  function labelThreshold() {
    return S.view.ppu >= 46 ? 1 : S.view.ppu >= 20 ? 2 : 3;
  }

  function layout() {
    var w = viewW();
    var thr = labelThreshold();
    var y0 = yearAt(gutter() - 400), y1 = yearAt(w + 400);
    var list = visible().filter(function (e) {
      if (e.year < y0 - 1 || e.year > y1 + 1) return false;
      if (S.view.ppu < 16 && e.importance < 3 && !S.q) return false;   // 远景只留必背；搜索时全显示
      return true;
    });

    var groups = {};
    lanes.forEach(function (l) { groups[l.id] = []; });
    list.forEach(function (e) { (groups[e.lane] || groups.event).push(e); });

    var chromeH = axisRow.offsetHeight + periodRow.offsetHeight +
      (document.querySelector('.foot') ? document.querySelector('.foot').offsetHeight : 0);
    var avail = Math.max(300, (stage.clientHeight || 700) - chromeH) - 14;
    var budget = Math.max(2, Math.min(16,
      Math.floor((avail / Math.max(1, lanes.length) - 12) / LANE_ROW)));
    /* 远景只显示必背时条目本来就少，不该再按行数丢弃 */
    if (S.view.ppu < 16 && !S.q) budget = Math.max(budget, 10);
    var q = S.q.toLowerCase();

    var arrs = lanes.map(function (l) {
      return (groups[l.id] || []).slice().sort(function (a, b) {
        return a.year - b.year || b.importance - a.importance;
      });
    });

    /* 行打包：同轨同年/近年的条目叠行，标签宽度用真实测量值防重叠。
       超出预算的行整行丢弃（而不是硬塞），保证一屏能看全七条轨道。 */
    function pack(arr, demote, budget) {
      var rows = [], items = [];
      /* 搜索时命中项优先占位，保证「搜到的看得见」 */
      var order = arr.slice();
      order.sort(function (a, b) {
        return (b.importance === 3 ? 1 : 0) - (a.importance === 3 ? 1 : 0);
      });
      if (S.q) {
        var kk = S.q.toLowerCase();
        order.sort(function (a, b) {
          var ma = matched(a) ? 0 : 1, mb = matched(b) ? 0 : 1;
          if (ma !== mb) return ma - mb;
          var ta = a.title.toLowerCase().indexOf(kk) >= 0 ? 0 : 1;
          var tb = b.title.toLowerCase().indexOf(kk) >= 0 ? 0 : 1;
          if (ta !== tb) return ta - tb;
          return a.year - b.year || b.importance - a.importance;
        });
      }
      order.forEach(function (e) {
        var x = xOf(e.year);
        if (x < gutter() - 2 || x > w + 380) return;
        var must = e.importance === 3 || (S.q && matched(e));
        var label = e.importance >= thr || must;
        var tw = label ? Math.ceil(textW(e.title, e.importance === 3)) + 20 : 16;
        var r = 0;
        while (rows[r] !== undefined && rows[r] + 7 > x) r++;
        if (demote && label && r >= budget && !must) {
          label = false; tw = 16; r = 0;
          while (rows[r] !== undefined && rows[r] + 7 > x) r++;
        }
        /* 必背/命中项即使超出预算也要放下，其余条目超预算才丢 */
        if (r >= budget && !must) return;
        rows[r] = x + tw;
        items.push({ e: e, x: x, r: r, label: label });
      });
      return { rows: rows, items: items };
    }

    function naturalH(p) {
      return Math.max(Math.max(1, p.rows.length) * LANE_ROW + 12, 52);
    }

    if (S.q) budget = Math.max(budget, 5);
    var packed = arrs.map(function (a) { return pack(a, false, budget); });
    var total = packed.reduce(function (s, p) { return s + naturalH(p); }, 0);

    if (total > avail) {
      packed = arrs.map(function (a) { return pack(a, true, budget); });
      total = packed.reduce(function (s, p) { return s + naturalH(p); }, 0);
    }

    /* 有余量则均分，让轨道铺满视口 */
    var add = Math.max(0, Math.floor((avail - total) / Math.max(1, lanes.length)));

    var html = '';
    var yCursor = 6;
    packed.forEach(function (p, i) {
      var l = lanes[i];
      var n = Math.max(1, p.rows.length);
      var h = naturalH(p) + add;
      var rowOff = Math.round((h - n * LANE_ROW) / 2);

      html += '<div class="lane-row" style="top:' + yCursor + 'px;height:' + h + 'px;--c:' + l.color + '">' +
        '<div class="lane-head">' + esc(l.name) + '</div>';
      p.items.forEach(function (it) {
        var e = it.e;
        var cls = 'ev imp' + e.importance + (it.label ? '' : ' dotonly');
        if (S.sel === e.id) cls += ' sel';
        if (!matched(e)) cls += ' miss';
        else if (q && S.q) cls += ' hit';
        if (S.mast[e.id] === 'ok') cls += ' mastered';
        if (S.mast[e.id] === 'todo') cls += ' todo';
        html += '<button type="button" class="' + cls + '" data-id="' + esc(e.id) + '" ' +
          'style="left:' + it.x.toFixed(1) + 'px;top:' + (rowOff + it.r * LANE_ROW + 1) + 'px;--c:' + l.color + '" ' +
          'title="' + esc(fmtDate(e.date) + ' · ' + e.title) + '">' +
          '<i class="dot"></i>' +
          (it.label ? '<span class="ev-title">' + esc(e.title) + '</span>' : '') +
          '</button>';
      });
      html += '</div>';
      yCursor += h;
    });

    tlEl.style.height = (yCursor + 14) + 'px';
    tlEl.innerHTML = '<div class="bands" id="bands"></div>' + html;

    /* 时期背景带 */
    var bands = $('#bands');
    var bh = '';
    periods.forEach(function (p, i) {
      var x1 = xOf(p.start), x2 = xOf(p.end);
      if (x2 < gutter() - 40 || x1 > w + 40) return;
      bh += '<div class="band' + (i % 2 ? ' alt' : '') + '" style="left:' + Math.max(x1, gutter()).toFixed(1) +
        'px;width:' + Math.max(0, x2 - Math.max(x1, gutter())).toFixed(1) + 'px"></div>';
    });
    bands.innerHTML = bh;

    $$('.ev', tlEl).forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        select(btn.dataset.id);
      });
      btn.addEventListener('dblclick', function (ev) {
        ev.stopPropagation();
        var e = byId[btn.dataset.id];
        if (e) centerOn(e.year);
      });
    });
  }

  /* ---------------- 渲染：移动端列表 ---------------- */
  function renderMob() {
    var sig = JSON.stringify([S.periods, S.lanes, S.tags, S.q]);
    if (sig === S.listSig) return;
    S.listSig = sig;
    var list = visible().filter(matched);
    if (!list.length) { mobEl.innerHTML = '<div class="mob-empty">没有符合条件的条目</div>'; return; }

    var pname = {};
    periods.forEach(function (p) { pname[p.id] = p.name; });

    /* 移动端上千条一次性插 DOM 会卡：先渲染前 120 条，滚动到底自动续 */
    mobEl.innerHTML = '<div id="mobList"></div>' +
      '<div id="mobMore" class="mob-more"></div>';
    var host = $('#mobList');
    var more = $('#mobMore');
    var i = 0, lastP = null, loading = false;

    function chunk(n) {
      loading = true;
      var html = '';
      var end = Math.min(list.length, i + n);
      for (; i < end; i++) {
        var e = list[i];
        if (e.period !== lastP) {
          lastP = e.period;
          html += '<div class="mob-period">' + esc(pname[e.period] || '') + '</div>';
        }
        html += '<div class="mob-row" data-id="' + esc(e.id) + '">' +
          '<div class="mob-y">' + esc(e.yLabel) + '</div>' +
          '<div><div class="mob-t">' + esc(e.title) + '</div>' +
          '<div class="mob-s">' + esc(e.summary) + '</div></div></div>';
      }
      host.insertAdjacentHTML('beforeend', html);
      more.textContent = i >= list.length
        ? '共 ' + list.length + ' 条，已全部显示'
        : '向下滚动加载更多（' + i + ' / ' + list.length + '）';
      loading = false;
    }

    host.addEventListener('click', function (ev) {
      var row = ev.target.closest ? ev.target.closest('.mob-row') : null;
      if (row) select(row.dataset.id);
    });

    mobEl.onscroll = function () {
      if (loading || i >= list.length) return;
      if (mobEl.scrollTop + mobEl.clientHeight > mobEl.scrollHeight - 300) chunk(120);
    };

    chunk(120);
  }

  /* ---------------- 渲染：统计 ---------------- */
  function renderStat() {
    var v = visible();   // 已含时期/轨道/标签筛选
    var ok = 0, todo = 0;
    v.forEach(function (e) {
      if (S.mast[e.id] === 'ok') ok++;
      else if (S.mast[e.id] === 'todo') todo++;
    });
    var m = v.filter(matched).length;
    statEl.innerHTML = '共 <b>' + events.length + '</b> 条 · 当前 <b>' + v.length + '</b>' +
      (S.q ? ' · 命中 <b>' + m + '</b>' : '') +
      ' · 已掌握 <b>' + ok + '</b> · 待复习 <b>' + todo + '</b>';
  }

  /* ---------------- 总渲染 ---------------- */
  var raf = 0;
  function render() {
    if (raf) return;
    raf = requestAnimationFrame(function () {
      raf = 0;
      renderAxis();
      renderPeriods();
      layout();
      renderMob();
      renderStat();
    });
  }

  /* ---------------- 详情抽屉 ---------------- */
  function relOf(e) {
    var out = [];
    events.forEach(function (o) {
      if (o.id === e.id) return;
      var share = o.people.some(function (p) { return e.people.indexOf(p) >= 0; }) ||
        o.schools.some(function (p) { return e.schools.indexOf(p) >= 0; });
      if (share) out.push(o);
    });
    return out.slice(0, 7);
  }

  function select(id) {
    var e = byId[id];
    if (!e) return;
    S.sel = id;
    $$('.ev.sel', tlEl).forEach(function (b) { b.classList.remove('sel'); });
    var btn = $('.ev[data-id="' + id.replace(/"/g, '\\"') + '"]', tlEl);
    if (btn) btn.classList.add('sel');

    var rel = relOf(e);
    var html =
      '<div class="d-head"><div class="d-main">' +
      '<div class="d-year">' + esc(fmtDate(e.date)) + '<span class="kind">' + esc(e.kind) + '</span></div>' +
        '<div class="d-sub">' + esc((periodName(e.period) || '') + ' · ' + laneName(e.lane)) + '</div>' +
      '<h2 class="d-title">' + esc(e.title) + '</h2>' +
      '</div><button class="d-close" id="dClose" type="button">×</button></div>' +
      '<div class="d-body">';

    if (e.summary) html += '<div class="d-sec"><div class="d-sum">' + esc(e.summary) + '</div></div>';
    if (e.detail) html += '<div class="d-sec"><div class="d-k">考点</div><div class="d-v">' + esc(e.detail) + '</div></div>';
    if (e.memory) html += '<div class="d-sec"><div class="d-k">记忆钩子</div><div class="d-mem">' + esc(e.memory) + '</div></div>';
    if (e.confuse) html += '<div class="d-sec"><div class="d-k">易混辨析</div><div class="d-warn">' + esc(e.confuse) + '</div></div>';

    if (e.people.length) {
      html += '<div class="d-sec"><div class="d-k">人物</div><div class="pills">' +
        e.people.map(function (p) { return '<span class="pill people">' + esc(p) + '</span>'; }).join('') +
        '</div></div>';
    }
    if (e.schools.length) {
      html += '<div class="d-sec"><div class="d-k">流派 · 思潮</div><div class="pills">' +
        e.schools.map(function (p) { return '<span class="pill">' + esc(p) + '</span>'; }).join('') +
        '</div></div>';
    }
    if (e.raw.chapter || e.raw.src) {
      var bookName = e.raw.src || '《中国现代文学三十年》';
      var where = e.raw.chapter
        ? (String(e.raw.chapter).indexOf('年表') >= 0 ? e.raw.chapter : e.raw.chapter + ' · 本章年表')
        : '';
      html += '<div class="d-sec"><div class="d-k">出处</div><div class="d-src">' +
        esc(bookName + (where ? '　' + where : '')) + '</div></div>';
    }
    if (e.tags.length) {
      html += '<div class="d-sec"><div class="d-k">标签</div><div class="pills">' +
        e.tags.map(function (p) { return '<span class="pill tag">' + esc(p) + '</span>'; }).join('') +
        '</div></div>';
    }
    if (rel.length) {
      html += '<div class="d-sec"><div class="d-k">相关条目</div><div class="d-rel">' +
        rel.map(function (o) {
          return '<button type="button" data-jump="' + esc(o.id) + '"><span class="y">' + esc(o.yLabel) +
            '</span><span class="t">' + esc(o.title) + '</span></button>';
        }).join('') + '</div></div>';
    }
    html += '</div>' +
      '<div class="d-actions">' +
      '<button class="btn" id="dMaster" type="button">' + (S.mast[e.id] === 'ok' ? '取消已掌握' : '标记已掌握') + '</button>' +
      '<button class="btn seal" id="dTodo" type="button">' + (S.mast[e.id] === 'todo' ? '取消待复习' : '加入待复习') + '</button>' +
      '<button class="btn" id="dGo" type="button">定位</button>' +
      '<button class="btn icon" id="dPrev" type="button" title="上一条 (←)">‹</button>' +
      '<button class="btn icon" id="dNext" type="button" title="下一条 (→)">›</button>' +
      '</div>';

    drawer.innerHTML = html;
    drawer.classList.add('open');
    drawer.dataset.id = e.id;

    $('#dClose').onclick = function () { closeDrawer(); };
    $('#dGo').onclick = function () { centerOn(e.year); };
    $('#dPrev').onclick = function () { step(-1); };
    $('#dNext').onclick = function () { step(1); };
    $('#dMaster').onclick = function () {
      if (S.mast[e.id] === 'ok') delete S.mast[e.id]; else S.mast[e.id] = 'ok';
      store('lit.mast', S.mast); select(e.id); render();
    };
    $('#dTodo').onclick = function () {
      if (S.mast[e.id] === 'todo') delete S.mast[e.id]; else S.mast[e.id] = 'todo';
      store('lit.mast', S.mast); select(e.id); render();
    };
    $$('[data-jump]', drawer).forEach(function (b) {
      b.onclick = function () {
        var t = byId[b.dataset.jump];
        if (t) { centerOn(t.year); select(t.id); }
      };
    });
  }

  function periodName(id) {
    var p = periods.filter(function (x) { return x.id === id; })[0];
    return p ? p.name : '';
  }
  function laneName(id) {
    var l = lanes.filter(function (x) { return x.id === id; })[0];
    return l ? l.name : '';
  }
  function step(dir) {
    if (!S.sel) return;
    var arr = visible();
    var i = -1;
    for (var k = 0; k < arr.length; k++) if (arr[k].id === S.sel) { i = k; break; }
    if (i < 0) return;
    var t = arr[i + dir];
    if (!t) return;
    centerOn(t.year);
    select(t.id);
  }

  function closeDrawer() {
    drawer.classList.remove('open');
    S.sel = null;
    $$('.ev.sel', tlEl).forEach(function (b) { b.classList.remove('sel'); });
  }

  /* ---------------- 自测 ---------------- */
  function shuffle(a) {
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }
  function maskTitle(e) {
    var s = e.summary || e.detail || '';
    s = s.replace(/《[^》]*》/g, '《____》');
    if (s.indexOf('____') < 0) s = '…… ' + s;
    return s;
  }

  function openQuiz() {
    var pool = visible().filter(function (e) { return e.importance >= 2; });
    if (!pool.length) { pool = visible().slice(); }
    if (!pool.length) { alert('当前筛选下没有条目，先放宽筛选。'); return; }
    S.quiz = { pool: shuffle(pool.slice()), i: 0, stage: 0, ok: 0, no: 0 };
    $('#quiz').classList.add('open');
    renderQuiz();
  }
  function renderQuiz() {
    var q = S.quiz;
    if (!q) return;
    var box = $('#quizBox');
    if (q.i >= q.pool.length) {
      box.innerHTML =
        '<div class="q-top"><div class="title">本轮结束</div><div class="q-prog">' + q.pool.length + ' 条</div></div>' +
        '<div class="q-card"><div class="q-year">' + q.ok + ' <small>会</small> / ' + q.no + ' <small>没记住</small></div>' +
        '<div class="q-ask">没记住的已自动进入「待复习」，可在时间轴上看朱砂圈标记。</div></div>' +
        '<div class="q-foot"><button class="btn" id="qAgain" type="button">再来一轮</button>' +
        '<button class="btn primary" id="qDone" type="button">完成</button></div>';
      $('#qAgain').onclick = function () { openQuiz(); };
      $('#qDone').onclick = closeQuiz;
      return;
    }
    var e = q.pool[q.i];
    var pct = q.i / q.pool.length * 100;
    var head = '<div class="q-year">' + esc(e.yLabel) + '<small>' + esc(e.kind) + '</small></div>';
    var body, foot;
    if (q.stage === 2) {
      body = '<div class="q-hint">答案</div>' +
        '<div class="q-answer">' + esc(e.title) + '</div>' +
        '<div class="q-answer-detail">' + esc(fmtDate(e.date)) + ' · ' + esc(e.kind) +
        (e.people.length ? ' · ' + esc(e.people.join('、')) : '') +
        (e.summary ? '<br>' + esc(e.summary) : '') +
        (e.detail ? '<br>' + esc(e.detail) : '') + '</div>';
      foot = '<button class="btn primary" id="qOk" type="button">会了</button>' +
        '<button class="btn seal" id="qNo" type="button">没记住</button>';
    } else {
      body = head +
        (q.stage === 1
          ? '<div class="q-mask"></div><div class="q-ask">' + esc(maskTitle(e)) + '</div>'
          : '<div class="q-hint" style="margin-top:10px">先自己回忆：这个时间点发生了什么？</div>') +
        '<div class="q-hint">这是哪一部作品／哪一件事？</div>';
      foot = (q.stage === 0 ? '<button class="btn" id="qHint" type="button">看提示</button>' : '') +
        '<button class="btn primary" id="qShow" type="button">显示答案</button>' +
        '<button class="btn" id="qSkip" type="button">跳过</button>';
    }
    box.innerHTML =
      '<div class="q-top"><div class="title">复习自测</div><div class="q-prog">' + (q.i + 1) + ' / ' + q.pool.length + '</div></div>' +
      '<div class="q-bar"><i style="width:' + pct + '%"></i></div>' +
      '<div class="q-card">' + body + '</div>' +
      '<div class="q-foot">' + foot + '</div>';

    if (q.stage === 2) {
      $('#qOk').onclick = function () { mark(e.id, 'ok'); q.ok++; q.i++; q.stage = 0; renderQuiz(); };
      $('#qNo').onclick = function () { mark(e.id, 'todo'); q.no++; q.i++; q.stage = 0; renderQuiz(); };
    } else {
      if ($('#qHint')) $('#qHint').onclick = function () { q.stage = 1; renderQuiz(); };
      $('#qShow').onclick = function () { q.stage = 2; renderQuiz(); };
      $('#qSkip').onclick = function () { q.i++; q.stage = 0; renderQuiz(); };
    }
  }
  function mark(id, v) {
    if (v) S.mast[id] = v; else delete S.mast[id];
    store('lit.mast', S.mast);
    render();
  }
  function closeQuiz() {
    $('#quiz').classList.remove('open');
    S.quiz = null;
    render();
  }

  /* ---------------- 打印 ---------------- */
  function buildPrint() {
    var pname = {};
    periods.forEach(function (p) { pname[p.id] = p.name + '（' + p.sub + '）'; });
    var list = visible().filter(matched);
    var html = '<div class="p-title">' + esc((D.meta && D.meta.title) || '中国现当代文学') + ' · 背诵版</div>' +
      '<div class="p-sub">共 ' + list.length + ' 条 · 按时期与年代排列 · 生成于 ' +
      new Date().toLocaleDateString('zh-CN') + '</div>';
    var cur = null;
    list.forEach(function (e) {
      if (e.period !== cur) {
        cur = e.period;
        html += '<div class="p-period">' + esc(pname[cur] || '') + '</div>';
      }
      html += '<div class="p-item"><div class="y">' + esc(fmtDate(e.date)) + '</div><div>' +
        '<span class="t">' + esc(e.title) + '</span>' +
        (e.summary ? ' <span class="s">— ' + esc(e.summary) + '</span>' : '') +
        (e.tags.indexOf('必背') >= 0 ? '<span class="tag">必背</span>' : '') +
        '</div></div>';
    });
    $('#printList').innerHTML = html;
  }

  /* ---------------- 交互绑定 ---------------- */
  function bindPan() {
    var drag = null;
    stage.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      if (e.target.closest('.ev')) return;
      drag = { x: e.clientX, start: S.view.start, moved: false };
      stage.setPointerCapture && stage.setPointerCapture(e.pointerId);
      if (e.target.closest('.axis-row')) axisRow.classList.add('dragging');
    });
    stage.addEventListener('pointermove', function (e) {
      if (!drag) return;
      var dx = e.clientX - drag.x;
      if (Math.abs(dx) > 3) drag.moved = true;
      if (!drag.moved) return;
      S.view.start = drag.start - dx / S.view.ppu;
      S.view = clampView();
      render();
    });
    var end = function () {
      drag = null;
      axisRow.classList.remove('dragging');
    };
    stage.addEventListener('pointerup', end);
    stage.addEventListener('pointercancel', end);

    stage.addEventListener('wheel', function (e) {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        zoomAt(e.deltaY > 0 ? 0.9 : 1.11, e.clientX);
        return;
      }
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY) + 2) {
        e.preventDefault();
        panBy(-e.deltaX / S.view.ppu * 1.0);
        return;
      }
      if (lanesEl.scrollHeight <= lanesEl.clientHeight + 2) {
        e.preventDefault();
        panBy(e.deltaY / S.view.ppu * 0.5);
      }
    }, { passive: false });
  }

  function bindKeys() {
    document.addEventListener('keydown', function (e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        if (e.key === 'Escape') { searchInput.blur(); }
        return;
      }
      if (e.key === 'Escape') { closeDrawer(); closeQuiz(); }
      else if (e.key === '/') { e.preventDefault(); searchInput.focus(); }
      else if (e.key === 'ArrowLeft') {
        if (S.sel && drawer.classList.contains('open')) step(-1);
        else panBy(-0.12 * (viewW() - gutter()) / S.view.ppu);
      }
      else if (e.key === 'ArrowRight') {
        if (S.sel && drawer.classList.contains('open')) step(1);
        else panBy(0.12 * (viewW() - gutter()) / S.view.ppu);
      }
      else if (e.key === '+' || e.key === '=') { zoomAt(1.25); }
      else if (e.key === '-') { zoomAt(0.8); }
      else if (e.key === '0') { fit(); }
    });
  }

  function bindSearch() {
    var t = 0;
    searchInput.addEventListener('input', function () {
      clearTimeout(t);
      t = setTimeout(function () {
        S.q = searchInput.value.trim();
        searchBox.classList.toggle('filled', !!S.q);
        render();
      }, 110);
    });
    searchInput.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      var cands = visible().filter(matched);
      /* 标题里直接含关键词的排在前面，避免跳到只在摘要里提到的条目 */
      var k = S.q.toLowerCase();
      cands.sort(function (a, b) {
        var ta = a.title.toLowerCase().indexOf(k) >= 0 ? 0 : 1;
        var tb = b.title.toLowerCase().indexOf(k) >= 0 ? 0 : 1;
        if (ta !== tb) return ta - tb;
        return a.year - b.year;
      });
      var hit = cands[0];
      if (hit) {
        if (S.view.ppu < 46) { S.view.ppu = 46; }
        centerOn(hit.year);
        select(hit.id);
      }
    });
    $('#qClear').onclick = function () {
      searchInput.value = '';
      S.q = '';
      searchBox.classList.remove('filled');
      render();
      searchInput.focus();
    };
  }

  /* ---------------- 启动 ---------------- */
  buildChips();
  bindPan();
  bindKeys();
  bindSearch();

  $('#zoomIn').onclick = function () { zoomAt(1.4); };
  $('#zoomOut').onclick = function () { zoomAt(0.71); };
  $('#fit').onclick = fit;
  $('#quizBtn').onclick = openQuiz;
  $('#printBtn').onclick = function () { buildPrint(); window.print(); };
  $('#quiz').addEventListener('click', function (e) {
    if (e.target.id === 'quiz') closeQuiz();
  });

  var rsz = 0;
  window.addEventListener('resize', function () {
    clearTimeout(rsz);
    rsz = setTimeout(function () { S.view = clampView(); render(); }, 120);
  });

  /* 首屏：若带 #条目id 则定位 */
  fit();
  var hid = decodeURIComponent((location.hash || '').replace(/^#/, ''));
  if (hid && byId[hid]) {
    centerOn(byId[hid].year);
    select(hid);
  } else {
    /* 首屏落在现代文学起点，全览略偏右 */
    S.view.start = Math.max(minYear - 2, minYear);
    S.view.ppu = Math.min(S.view.ppu, fitPpu() * 2.2);
    S.view = clampView();
    render();
  }

  window.LIT = { events: events, select: select, zoomAt: zoomAt, fit: fit, state: S };
})();
