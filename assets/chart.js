/* Presentation layer — tabs, expandable cards, and the three chart templates.
 *
 * Inlined into site/index.html by build.py (assets/ is source; site/ is a build
 * artifact). Hand-rolled SVG, no libraries, no keys, no storage of any kind.
 * Tab + expanded-card state live in the URL hash only.
 *
 * Honesty rules encoded here, not left to taste:
 *  - gaps in a series render as line BREAKS (never interpolated), with a note;
 *  - definition changes render as labelled dashed markers (never smoothed);
 *  - bars are always zero-based; %-change and index views baseline at 0/100;
 *  - every chart has a Table view twin and a link to the raw stored series.
 *
 * Charts fetch their payload (site/d/<id>.json) on first expand — the homepage
 * stays light; history loads only when someone asks for it.
 */
(function () {
  'use strict';
  document.documentElement.classList.remove('no-js');

  var CLR = { ink:'#ffffff', sec:'#c3c2b7', mut:'#898781', grid:'#2c2c2a', axis:'#4a4a47',
              surface:'#1a1a19', dash:'#6b6965' };
  var MONTH = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

  /* ---------- formatting ---------- */
  function fnum(v) { return Math.round(v).toLocaleString('en-US'); }
  function fmt(v, kind, axis) {
    if (v == null || isNaN(v)) return '—';
    var a = Math.abs(v), s = v < 0 ? '−' : '';
    switch (kind) {
      case 'pct':     return (Math.round(v * 10) / 10) + '%';
      case 'pct2':    return (Math.round(v * 100) / 100) + '%';
      case 'pctsign': return (v > 0 ? '+' : (v < 0 ? '−' : '')) +
                             (axis ? '' + Math.round(a * 10) / 10 : a.toFixed(1)) + '%';
      case 'usd2':    return s + '$' + a.toFixed(2);
      case 'usdB':    return s + '$' + fnum(a) + 'B';
      case 'usd':
        if (a >= 1e12) return s + '$' + (a / 1e12).toFixed(axis ? 0 : 1) + 'T';
        if (a >= 1e9)  return s + '$' + (a / 1e9).toFixed(0) + 'B';
        return s + '$' + fnum(a);
      case 'count':   return axis ? (a >= 1e6 ? (v / 1e6).toFixed(1).replace(/\.0$/, '') + 'M'
                                   : a >= 1e4 ? Math.round(v / 1e3) + 'k'
                                   : a >= 1e3 ? (v / 1e3).toFixed(1).replace(/\.0$/, '') + 'k' : fnum(v))
                                  : fnum(v);
      case 'idx':     return (Math.round(v * 10) / 10) + '';
      default:        return '' + v;
    }
  }
  function ticks(lo, hi, n) {
    var span = (hi - lo) || 1, step = Math.pow(10, Math.floor(Math.log(span / n) / Math.LN10));
    var err = span / n / step; step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
    var out = [], v = Math.ceil(lo / step) * step;
    for (; v <= hi + 1e-9; v += step) out.push(Math.round(v * 1e9) / 1e9);
    return out;
  }
  function el(tag, attrs) {
    var e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function halo(attrs) {  /* surface-colored text halo: legible over any line */
    attrs.stroke = CLR.surface; attrs['stroke-width'] = 3;
    attrs['paint-order'] = 'stroke'; attrs['stroke-linejoin'] = 'round';
    return attrs;
  }
  function div(cls, parent) {
    var d = document.createElement('div'); if (cls) d.className = cls;
    if (parent) parent.appendChild(d); return d;
  }
  function txt(node, s) { node.textContent = s; return node; }
  function dLab(x) { var d = new Date(x); return MONTH[d.getUTCMonth()] + ' ' + d.getUTCFullYear(); }

  function xTicks(fx, x0, x1) {
    var out = [];
    if (fx.xType === 'months') {
      for (var m = 0; m <= x1; m += 6) out.push({ x: m, lab: '' + m });
      return out;
    }
    var y0 = new Date(x0).getUTCFullYear(), y1 = new Date(x1).getUTCFullYear(), span = y1 - y0;
    if (span >= 3) {
      var step = Math.max(1, Math.ceil(span / 6));
      for (var y = Math.ceil(y0 / step) * step; y <= y1; y += step) {
        var t = Date.UTC(y, 0, 1); if (t >= x0 - 1 && t <= x1) out.push({ x: t, lab: '' + y });
      }
    } else {
      var d = new Date(x0); d.setUTCDate(1);
      var stepM = span >= 1 ? 4 : 2;
      while (+d < x0) d.setUTCMonth(d.getUTCMonth() + 1);
      while (+d <= x1) {
        out.push({ x: +d, lab: MONTH[d.getUTCMonth()] + ' ’' + ('' + d.getUTCFullYear()).slice(2) });
        d.setUTCMonth(d.getUTCMonth() + stepM);
      }
    }
    return out.filter(function (t) { return t.x >= x0 - 1; });
  }

  /* split a series into gap-free segments — holes render as breaks, never bridged */
  function segments(pts) {
    if (!pts.length) return [];
    var xs = pts.map(function (p) { return p[0]; }), steps = [];
    for (var i = 1; i < xs.length; i++) steps.push(xs[i] - xs[i - 1]);
    steps.sort(function (a, b) { return a - b; });
    var med = steps.length ? steps[Math.floor(steps.length / 2)] : 0;
    var segs = [], cur = [pts[0]];
    for (var j = 1; j < pts.length; j++) {
      if (med && (xs[j] - xs[j - 1]) > 1.75 * med) { segs.push(cur); cur = []; }
      cur.push(pts[j]);
    }
    segs.push(cur);
    return segs;
  }

  /* ---------- line template (own-history · term-aligned · vs-benchmark) ---------- */
  function lineChart(box, fx, state) {
    box.innerHTML = '';
    var W = Math.max(300, box.clientWidth), narrow = W < 540;
    var H = narrow ? 240 : 305;
    var capH = (fx.xType === 'months') ? 16 : 0;

    var sers = fx.series.map(function (s) {
      var pts = s.pts;
      if (state.range === 'term' && fx.termStart) pts = pts.filter(function (p) { return p[0] >= fx.termStart; });
      return { label: s.label, color: s.color, pts: pts };
    }).filter(function (s) { return s.pts.length; });

    var allY = [], allX = [];
    sers.forEach(function (s) { s.pts.forEach(function (p) { allX.push(p[0]); allY.push(p[1]); }); });
    (fx.dots || []).forEach(function (d) { allX.push(d.x); allY.push(d.y); });
    if (fx.benchmark != null) allY.push(fx.benchmark);
    var x0 = fx.xType === 'months' ? 0 : Math.min.apply(null, allX);
    var x1 = fx.xType === 'months' ? (fx.xMax || 48) : Math.max.apply(null, allX);
    var yMin = Math.min.apply(null, allY), yMax = Math.max.apply(null, allY);
    if (fx.zeroBase !== false) { if (yMin > 0) yMin = 0; if (yMax < 0) yMax = 0; }
    if (fx.baseline != null) { yMin = Math.min(yMin, fx.baseline); yMax = Math.max(yMax, fx.baseline); }
    var pad = (yMax - yMin) * 0.07 || 1;
    yMax += pad; if (yMin < 0) yMin -= pad;

    var yT = ticks(yMin, yMax, narrow ? 4 : 5);
    var maxYLab = yT.reduce(function (m, v) { return Math.max(m, fmt(v, fx.fmtAxis || fx.fmt, true).length); }, 0);
    var endLab = fx.direct && sers.length > 1 && !narrow;
    var endW = 0;
    if (endLab) sers.forEach(function (s) {
      var lastx = s.pts[s.pts.length - 1][0];
      if ((x1 - lastx) / (x1 - x0 || 1) > 0.06) return;  /* short lines label at their own dot */
      var L = (s.label + '  ' + fmt(s.pts[s.pts.length - 1][1], fx.fmt)).length * 7.2 + 20;
      endW = Math.max(endW, L);
    });
    var ml = maxYLab * 6.8 + 14, mr = endLab ? Math.min(170, Math.max(14, endW)) : 14, mt = 14, mb = 26 + capH;
    var pw = W - ml - mr, ph = H - mt - mb;
    var X = function (v) { return ml + (v - x0) / (x1 - x0 || 1) * pw; };
    var Y = function (v) { return mt + (yMax - v) / (yMax - yMin || 1) * ph; };

    var svg = el('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img',
                          'aria-label': fx.chartTitle });
    yT.forEach(function (v) {
      svg.appendChild(el('line', { x1: ml, x2: ml + pw, y1: Y(v), y2: Y(v), stroke: CLR.grid, 'stroke-width': 1 }));
      var t = el('text', { x: ml - 8, y: Y(v) + 4, 'text-anchor': 'end', fill: CLR.mut,
                           'font-size': '11', style: 'font-variant-numeric:tabular-nums' });
      t.textContent = fmt(v, fx.fmtAxis || fx.fmt, true);
      svg.appendChild(t);
    });
    if (yMin < 0 && yMax > 0)
      svg.appendChild(el('line', { x1: ml, x2: ml + pw, y1: Y(0), y2: Y(0), stroke: CLR.axis, 'stroke-width': 1 }));
    xTicks(fx, x0, x1).forEach(function (tk) {
      var tx = X(tk.x), anchor = 'middle';
      if (tx < ml + 16) anchor = 'start';
      if (tx > ml + pw - 16) anchor = 'end';
      var t = el('text', { x: tx, y: H - 10 - capH, 'text-anchor': anchor, fill: CLR.mut, 'font-size': '11' });
      t.textContent = tk.lab; svg.appendChild(t);
    });
    if (capH) {
      var cap = el('text', { x: ml + pw / 2, y: H - 4, 'text-anchor': 'middle', fill: CLR.mut, 'font-size': '10.5' });
      cap.textContent = 'Months in office'; svg.appendChild(cap);
    }
    /* vertical markers: inauguration (solid) · definition breaks (dashed) — marked, never smoothed */
    (fx.markers || []).forEach(function (mk) {
      if (mk.x < x0 || mk.x > x1) return;
      var lx = X(mk.x);
      svg.appendChild(el('line', { x1: lx, x2: lx, y1: mt, y2: mt + ph, stroke: CLR.dash,
        'stroke-width': 1, 'stroke-dasharray': mk.kind === 'break' ? '4 4' : 'none', opacity: .85 }));
      var right = lx > ml + pw * 0.62;
      var t = el('text', halo({ x: right ? lx - 5 : lx + 5, y: mt + 10, 'text-anchor': right ? 'end' : 'start',
                           fill: CLR.mut, 'font-size': '10.5', 'font-weight': '600' }));
      t.textContent = mk.label; svg.appendChild(t);
    });
    (fx.gaps || []).forEach(function (g) {
      if (g.x < x0 || g.x > x1) return;
      var gx = X(g.x), right = gx > ml + pw * 0.6;
      var t = el('text', halo({ x: right ? gx - 5 : gx + 5, y: mt + ph * 0.16, 'text-anchor': right ? 'end' : 'start',
                           fill: CLR.mut, 'font-size': '10.5', 'font-style': 'italic' }));
      t.textContent = g.label; svg.appendChild(t);
    });
    if (sers.length === 1 && fx.area) {
      var base = Y(Math.max(0, yMin));
      segments(sers[0].pts).forEach(function (seg) {
        if (seg.length < 2) return;
        var d = 'M' + X(seg[0][0]) + ' ' + base;
        seg.forEach(function (p) { d += ' L' + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); });
        d += ' L' + X(seg[seg.length - 1][0]) + ' ' + base + ' Z';
        svg.appendChild(el('path', { d: d, fill: sers[0].color, opacity: 0.09 }));
      });
    }
    if (fx.benchmark != null) {
      svg.appendChild(el('line', { x1: ml, x2: ml + pw, y1: Y(fx.benchmark), y2: Y(fx.benchmark),
        stroke: CLR.sec, 'stroke-width': 1.5, 'stroke-dasharray': '5 4' }));
      var bt = el('text', halo({ x: ml + pw - 4, y: Y(fx.benchmark) - 6, 'text-anchor': 'end',
                            fill: CLR.sec, 'font-size': '11', 'font-weight': '600' }));
      bt.textContent = fx.benchmarkLabel || ('' + fx.benchmark); svg.appendChild(bt);
    }
    sers.forEach(function (s) {
      segments(s.pts).forEach(function (seg) {
        if (seg.length === 1) {
          svg.appendChild(el('circle', { cx: X(seg[0][0]), cy: Y(seg[0][1]), r: 3, fill: s.color }));
          return;
        }
        var d = '';
        seg.forEach(function (p, i) { d += (i ? ' L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); });
        svg.appendChild(el('path', { d: d, fill: 'none', stroke: s.color, 'stroke-width': 2,
          'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
      });
    });
    /* standalone comparison dots (e.g. a prior president's same-point total pending full backfill) */
    (fx.dots || []).forEach(function (dt) {
      svg.appendChild(el('circle', { cx: X(dt.x), cy: Y(dt.y), r: 4.5, fill: dt.color,
        stroke: CLR.surface, 'stroke-width': 2 }));
      if (!narrow) {
        var right = X(dt.x) > ml + pw * 0.6;
        var t = el('text', halo({ x: right ? X(dt.x) - 9 : X(dt.x) + 9, y: Y(dt.y) + 4,
          'text-anchor': right ? 'end' : 'start', fill: CLR.sec, 'font-size': '11', 'font-weight': '600' }));
        t.textContent = dt.label; svg.appendChild(t);
      }
    });
    var ends = sers.map(function (s) {
      var p = s.pts[s.pts.length - 1];
      return { s: s, x: X(p[0]), y: Y(p[1]), v: p[1] };
    });
    ends.forEach(function (e) {
      svg.appendChild(el('circle', { cx: e.x, cy: e.y, r: 4.5, fill: e.s.color,
        stroke: CLR.surface, 'stroke-width': 2 }));
    });
    if (endLab) {
      var slots = ends.slice().sort(function (a, b) { return a.y - b.y; });
      slots.forEach(function (e) { e.ly = e.y; });
      for (var k = 1; k < slots.length; k++) {
        var prev = slots[k - 1], cur = slots[k];
        if (Math.abs(cur.x - prev.x) < 80 && cur.ly - prev.ly < 15) cur.ly = prev.ly + 15;
      }
      var over = slots.length ? slots[slots.length - 1].ly - (mt + ph + 4) : 0;
      if (over > 0) slots.forEach(function (e) { if (e.ly > mt + 10) e.ly -= over; });
      slots.forEach(function (e) {
        var text = e.s.label + '  ' + fmt(e.v, fx.fmt);
        var tw = text.length * 6.9, lx = e.x + 9, anchor = 'start';
        if (lx + tw > W - 4) { lx = e.x - 9; anchor = 'end'; }
        if (Math.abs(e.ly - e.y) > 8)
          svg.appendChild(el('line', { x1: e.x + (anchor === 'start' ? 6 : -6), y1: e.y,
            x2: lx + (anchor === 'start' ? -2 : 2), y2: e.ly, stroke: CLR.axis, 'stroke-width': 1 }));
        var t = el('text', halo({ x: lx, y: e.ly + 4, 'text-anchor': anchor, fill: CLR.sec,
          'font-size': '11.5', 'font-weight': '600' }));
        t.textContent = text;
        svg.appendChild(t);
      });
    }
    box.appendChild(svg);
    attachHover(box, svg, fx, sers, { X: X, Y: Y, ml: ml, pw: pw, mt: mt, ph: ph, x0: x0, x1: x1 });
  }

  /* ---------- bar template (annual counts) ---------- */
  function barChart(box, fx, state) {
    box.innerHTML = '';
    var W = Math.max(300, box.clientWidth), narrow = W < 540;
    var H = narrow ? 240 : 305;
    var pts = fx.series[0].pts, color = fx.series[0].color;
    var yMax = Math.max.apply(null, pts.map(function (p) { return p[1] || 0; })) * 1.12;
    var yT = ticks(0, yMax, narrow ? 4 : 5);
    var maxYLab = yT.reduce(function (m, v) { return Math.max(m, fmt(v, fx.fmt, true).length); }, 0);
    var ml = maxYLab * 6.8 + 14, mr = 8, mt = 16, mb = 26;
    var pw = W - ml - mr, ph = H - mt - mb;
    var Y = function (v) { return mt + (yMax - v) / yMax * ph; };
    var band = pw / pts.length, bw = Math.min(24, band * 0.62);
    var svg = el('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': fx.chartTitle });
    yT.forEach(function (v) {
      svg.appendChild(el('line', { x1: ml, x2: ml + pw, y1: Y(v), y2: Y(v), stroke: CLR.grid, 'stroke-width': 1 }));
      var t = el('text', { x: ml - 8, y: Y(v) + 4, 'text-anchor': 'end', fill: CLR.mut, 'font-size': '11',
                           style: 'font-variant-numeric:tabular-nums' });
      t.textContent = fmt(v, fx.fmt, true); svg.appendChild(t);
    });
    var bars = [];
    pts.forEach(function (p, i) {
      var cx = ml + band * i + band / 2;
      if (p[1] == null) {  /* a year with no published figure: labelled hole, never a zero bar */
        var gl = el('text', { x: cx, y: mt + ph + 16, 'text-anchor': 'middle', fill: CLR.mut, 'font-size': '10.5' });
        gl.textContent = p[2]; svg.appendChild(gl);
        var gm = el('text', { x: cx, y: mt + ph - 6, 'text-anchor': 'middle', fill: CLR.mut,
                              'font-size': '10', 'font-style': 'italic' });
        gm.textContent = '·'; svg.appendChild(gm);
        bars.push({ el: gm, cx: cx, y: mt + ph - 20, p: p, hole: true });
        return;
      }
      var x = cx - bw / 2, y = Y(p[1]), h = mt + ph - y;
      var r = Math.min(4, h);
      var d = 'M' + x + ' ' + (mt + ph) + ' L' + x + ' ' + (y + r) + ' Q' + x + ' ' + y + ' ' + (x + r) + ' ' + y +
              ' L' + (x + bw - r) + ' ' + y + ' Q' + (x + bw) + ' ' + y + ' ' + (x + bw) + ' ' + (y + r) +
              ' L' + (x + bw) + ' ' + (mt + ph) + ' Z';
      var bar = el('path', { d: d, fill: color });
      svg.appendChild(bar);
      bars.push({ el: bar, cx: cx, y: y, p: p });
      var lab = el('text', { x: cx, y: mt + ph + 16, 'text-anchor': 'middle', fill: CLR.mut, 'font-size': '10.5' });
      lab.textContent = (narrow && i % 2 && pts.length > 8) ? '' : p[2];
      svg.appendChild(lab);
      if ((fx.labelIdx || []).indexOf(i) >= 0) {
        var vt = el('text', halo({ x: cx, y: y - 7, 'text-anchor': 'middle', fill: CLR.sec, 'font-size': '11', 'font-weight': '650' }));
        vt.textContent = fmt(p[1], fx.fmt); svg.appendChild(vt);
      }
    });
    box.appendChild(svg);
    var tip = div('tooltip', box);
    function showBar(i) {
      var b = bars[i]; if (!b) return;
      bars.forEach(function (o) { if (!o.hole) o.el.setAttribute('opacity', o === b ? '1' : '0.55'); });
      tip.innerHTML = '';
      txt(div('tt-x', tip), b.p[3] || b.p[2]);
      var row = div('tt-row', tip);
      var key = div('tt-key', row); key.style.borderColor = color;
      txt(div('tt-val', row), b.hole ? 'not yet published' : fmt(b.p[1], fx.fmt));
      tip.style.display = 'block';
      var tw = tip.offsetWidth;
      tip.style.left = Math.min(Math.max(4, b.cx - tw / 2), W - tw - 4) + 'px';
      tip.style.top = Math.max(2, b.y - tip.offsetHeight - 12) + 'px';
    }
    function hideBar() { tip.style.display = 'none'; bars.forEach(function (o) { if (!o.hole) o.el.setAttribute('opacity', '1'); }); }
    var idx = -1;
    svg.addEventListener('pointermove', function (ev) {
      var r = svg.getBoundingClientRect();
      var i = Math.floor((ev.clientX - r.left - ml) / band);
      if (i >= 0 && i < bars.length) { idx = i; showBar(i); } else hideBar();
    });
    svg.addEventListener('pointerleave', hideBar);
    box.tabIndex = 0;
    box.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowRight') { idx = Math.min(bars.length - 1, idx + 1); showBar(idx); ev.preventDefault(); }
      else if (ev.key === 'ArrowLeft') { idx = Math.max(0, idx - 1); showBar(idx); ev.preventDefault(); }
      else if (ev.key === 'Escape') hideBar();
    });
  }

  /* ---------- crosshair + tooltip: snaps to nearest X, lists every series ---------- */
  function attachHover(box, svg, fx, sers, g) {
    var union = {};
    sers.forEach(function (s) { s.pts.forEach(function (p) { union[fx.xType === 'months' ? Math.round(p[0]) : p[0]] = 1; }); });
    var xs = Object.keys(union).map(Number).sort(function (a, b) { return a - b; });
    if (!xs.length) return;
    var steps = []; for (var i = 1; i < xs.length; i++) steps.push(xs[i] - xs[i - 1]);
    steps.sort(function (a, b) { return a - b; });
    var tol = (steps[Math.floor(steps.length / 2)] || 1) * 0.55;
    var cross = el('line', { y1: g.mt, y2: g.mt + g.ph, stroke: CLR.axis, 'stroke-width': 1, visibility: 'hidden' });
    svg.appendChild(cross);
    var tip = div('tooltip', box);
    var idx = -1;
    function show(i) {
      var x = xs[i]; if (x == null) return;
      idx = i;
      cross.setAttribute('x1', g.X(x)); cross.setAttribute('x2', g.X(x));
      cross.setAttribute('visibility', 'visible');
      tip.innerHTML = '';
      txt(div('tt-x', tip), fx.xType === 'months' ? ('Month ' + x + ' of term') : dLab(x));
      sers.forEach(function (s) {
        var best = null, bd = Infinity;
        s.pts.forEach(function (p) { var d = Math.abs(p[0] - x); if (d < bd) { bd = d; best = p; } });
        if (!best || bd > tol) return;
        var row = div('tt-row', tip);
        var key = div('tt-key', row); key.style.borderColor = s.color;
        txt(div('tt-val', row), fmt(best[1], fx.fmt));
        if (sers.length > 1) txt(div('tt-lab', row), s.label);
      });
      tip.style.display = 'block';
      var px = g.X(x), left = px + 14;
      if (left + tip.offsetWidth > box.clientWidth - 4) left = px - tip.offsetWidth - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = (g.mt + 8) + 'px';
    }
    function hide() { cross.setAttribute('visibility', 'hidden'); tip.style.display = 'none'; }
    svg.addEventListener('pointermove', function (ev) {
      var r = svg.getBoundingClientRect();
      var vx = (ev.clientX - r.left - g.ml) / (g.pw || 1) * (g.x1 - g.x0) + g.x0;
      var bi = 0, bd = Infinity;
      xs.forEach(function (x, i) { var d = Math.abs(x - vx); if (d < bd) { bd = d; bi = i; } });
      show(bi);
    });
    svg.addEventListener('pointerleave', hide);
    box.tabIndex = 0;
    box.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowRight') { show(Math.min(xs.length - 1, (idx < 0 ? xs.length - 1 : idx + 1))); ev.preventDefault(); }
      else if (ev.key === 'ArrowLeft') { show(Math.max(0, (idx < 0 ? xs.length - 1 : idx - 1))); ev.preventDefault(); }
      else if (ev.key === 'Escape') hide();
    });
    box.addEventListener('focus', function () { if (idx < 0) show(xs.length - 1); });
  }

  /* ---------- table view: the no-hover, screen-reader-clean twin ---------- */
  function buildTable(box, fx) {
    box.innerHTML = '';
    var wrapT = div('dtable', box);
    var table = document.createElement('table');
    var thead = document.createElement('thead'), trh = document.createElement('tr');
    var h0 = document.createElement('th');
    h0.textContent = fx.template === 'bars' ? 'Period' : (fx.xType === 'months' ? 'Month of term' : 'Date');
    trh.appendChild(h0);
    fx.series.forEach(function (s) {
      var th = document.createElement('th');
      th.textContent = fx.series.length > 1 ? s.label : (fx.unitLabel || 'Value');
      trh.appendChild(th);
    });
    thead.appendChild(trh); table.appendChild(thead);
    var tbody = document.createElement('tbody');
    if (fx.template === 'bars') {
      fx.series[0].pts.slice().reverse().forEach(function (p) {
        var tr = document.createElement('tr');
        var td0 = document.createElement('td'); td0.textContent = p[3] || p[2]; tr.appendChild(td0);
        var td = document.createElement('td'); td.textContent = fmt(p[1], fx.fmt); tr.appendChild(td);
        tbody.appendChild(tr);
      });
    } else {
      var union = {};
      fx.series.forEach(function (s, si) {
        s.pts.forEach(function (p) {
          var k = fx.xType === 'months' ? Math.round(p[0]) : p[0];
          (union[k] = union[k] || {})[si] = p[1];
        });
      });
      Object.keys(union).map(Number).sort(function (a, b) { return b - a; }).forEach(function (k) {
        var tr = document.createElement('tr');
        var td0 = document.createElement('td');
        td0.textContent = fx.xType === 'months' ? ('Month ' + k) : dLab(k);
        tr.appendChild(td0);
        fx.series.forEach(function (s, si) {
          var td = document.createElement('td');
          td.textContent = union[k][si] != null ? fmt(union[k][si], fx.fmt) : '—';
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }
    table.appendChild(tbody); wrapT.appendChild(table);
  }

  /* ---------- expanded-card assembly (shared by all three templates) ---------- */
  function buildDetail(card, fx) {
    var detail = card.querySelector('.detail');
    detail.innerHTML = '';
    var state = { range: 'full', view: 'chart' };
    var hasChart = fx.series && fx.series.length;

    var head = div('chart-head', detail);
    txt(div('chart-title', head), fx.chartTitle || '');
    var ctrl = div('chart-ctrl', head);
    var btns = [];
    function mkBtn(lab, on, active) {
      var b = document.createElement('button'); b.className = 'ctrl-btn' + (active ? ' active' : '');
      b.type = 'button'; b.textContent = lab; b.addEventListener('click', on); ctrl.appendChild(b); return b;
    }
    if (hasChart && fx.rangeToggle) {
      var bT = mkBtn('This term', function () { state.range = 'term'; sync(); }, false);
      var bF = mkBtn('Full history', function () { state.range = 'full'; sync(); }, true);
      btns.push([bT, 'range', 'term'], [bF, 'range', 'full']);
    }
    if (hasChart) {
      var bC = mkBtn('Chart', function () { state.view = 'chart'; sync(); }, true);
      var bTab = mkBtn('Table', function () { state.view = 'table'; sync(); }, false);
      btns.push([bC, 'view', 'chart'], [bTab, 'view', 'table']);
    }

    if (hasChart && fx.series.length > 1) {
      var lg = div('legend', detail);
      fx.series.forEach(function (s) {
        var item = div('lg', lg);
        var key = div('key', item); key.style.borderTopColor = s.color;
        item.appendChild(document.createTextNode(s.label));
      });
    }

    var box = div('chart-box', detail);
    box.setAttribute('role', 'application');
    box.setAttribute('aria-label', (fx.chartTitle || 'chart') + ' — arrow keys read values');

    function sync() {
      btns.forEach(function (b) { b[0].classList.toggle('active', state[b[1]] === b[2]); });
      if (!hasChart) {
        box.innerHTML = '';
        var ac = div('accrue', box);   /* sparse metric: the honest empty state */
        var b1 = document.createElement('b'); b1.textContent = fx.accrueTitle || 'History accrues from here';
        ac.appendChild(b1);
        ac.appendChild(document.createTextNode(fx.accrueBody || ''));
        return;
      }
      if (state.view === 'table') buildTable(box, fx);
      else if (fx.template === 'bars') barChart(box, fx, state);
      else lineChart(box, fx, state);
    }
    sync();

    var fur = div('furniture', detail);
    var f1 = div('fbox', fur);
    var h41 = document.createElement('h4'); h41.textContent = 'How the presidency influences this'; f1.appendChild(h41);
    var pc = document.createElement('p');
    var lc = document.createElement('span'); lc.className = 'flabel'; lc.textContent = 'Channels: ';
    pc.appendChild(lc); pc.appendChild(document.createTextNode(fx.channels || '')); f1.appendChild(pc);
    var pl = document.createElement('p');
    var ll = document.createElement('span'); ll.className = 'flabel'; ll.textContent = 'Limits: ';
    pl.appendChild(ll); pl.appendChild(document.createTextNode(fx.limits || '')); f1.appendChild(pl);
    var f2 = div('fbox', fur);
    var h42 = document.createElement('h4'); h42.textContent = 'Read this number carefully'; f2.appendChild(h42);
    (fx.caveats || []).forEach(function (c) {
      var p = document.createElement('p'); p.textContent = c; f2.appendChild(p);
    });

    var meta = div('detail-meta', detail);
    txt(div('', meta), 'Data as of ' + fx.asOf);
    txt(div('', meta), 'Updates ' + fx.cadence);
    var a = document.createElement('a'); a.href = fx.srcUrl; a.target = '_blank'; a.rel = 'noopener';
    a.textContent = 'Source: ' + fx.srcName + ' ↗'; meta.appendChild(a);
    var j = document.createElement('a'); j.href = 'd/' + fx.id + '.json'; j.target = '_blank'; j.rel = 'noopener';
    j.textContent = 'Series (JSON)'; j.title = 'The chart’s exact data payload, as served';
    meta.appendChild(j);

    if (window.ResizeObserver) {
      var t; new ResizeObserver(function () {
        clearTimeout(t); t = setTimeout(function () {
          if (!detail.hidden && state.view === 'chart' && hasChart) sync();
        }, 160);
      }).observe(detail);
    }
  }

  /* ---------- expand / collapse (payload fetched on first expand) ---------- */
  var inflight = {};
  function loadDetail(card, cb) {
    var id = card.getAttribute('data-id');
    if (card._fx) return cb(card._fx);
    if (inflight[id]) return;
    inflight[id] = true;
    fetch('d/' + id + '.json').then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (fx) {
      card._fx = fx; inflight[id] = false; cb(fx);
    }).catch(function () {
      inflight[id] = false;
      var detail = card.querySelector('.detail');
      detail.innerHTML = '';
      var p = div('accrue', detail);
      txt(p, 'History couldn’t load just now. The figures above are complete; reload to try again.');
      detail.hidden = false; card.classList.add('open'); setLabel(card, true);
    });
  }
  function setLabel(card, open) {
    var span = card.querySelector('.expand-btn span');
    if (span) span.textContent = open ? 'Collapse' : 'History & context';
    var b = card.querySelector('.expand-btn');
    if (b) b.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  function toggle(card, forceOpen) {
    var detail = card.querySelector('.detail');
    var open = card.classList.contains('open');
    if (open && forceOpen) return;
    if (open) { card.classList.remove('open'); detail.hidden = true; setLabel(card, false); return; }
    loadDetail(card, function (fx) {
      if (!detail.dataset.built) { buildDetail(card, fx); detail.dataset.built = '1'; }
      card.classList.add('open'); detail.hidden = false; setLabel(card, true);
    });
  }
  document.querySelectorAll('.tile[data-id]').forEach(function (card) {
    var btn = card.querySelector('.expand-btn');
    if (btn) btn.addEventListener('click', function () { toggle(card); });
  });

  /* ---------- category tabs — All default; state in the URL hash, no storage ---------- */
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'));
  var sections = Array.prototype.slice.call(document.querySelectorAll('.category'));
  function activate(slug, scroll) {
    tabs.forEach(function (t) { t.classList.toggle('active', t.dataset.tab === slug); });
    sections.forEach(function (s) { s.hidden = (slug !== 'all' && s.dataset.tab !== slug); });
    if (scroll) {
      var bar = document.getElementById('tabs');
      if (bar) window.scrollTo({ top: bar.offsetTop - 12, behavior: 'smooth' });
    }
  }
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      var slug = t.dataset.tab;
      if (history.replaceState) history.replaceState(null, '', slug === 'all' ? '#' : '#t/' + slug);
      var bar = document.getElementById('tabs');
      activate(slug, bar && window.scrollY > bar.offsetTop);
    });
  });
  function route() {
    var h = location.hash || '';
    if (h.indexOf('#m/') === 0) {
      var id = h.slice(3), card = document.getElementById('card-' + id);
      if (card && card.getAttribute('data-id')) {
        var sec = card.closest('.category');
        activate(sec ? sec.dataset.tab : 'all', false);
        toggle(card, true);
        setTimeout(function () { card.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
        return;
      }
    }
    if (h.indexOf('#t/') === 0) { activate(h.slice(3), false); return; }
    activate('all', false);
  }
  window.addEventListener('hashchange', route);
  route();

  /* ---------- client-side freshness (unchanged behavior from v1 board) ---------- */
  var now = new Date();
  document.querySelectorAll('.tile[data-stale-after]').forEach(function (elx) {
    var sa = new Date(elx.getAttribute('data-stale-after') + 'T23:59:59Z');
    if (isNaN(sa)) return;
    if (now > sa) {
      elx.classList.add('is-stale');
      var f = elx.querySelector('.stale-flag');
      if (f) f.hidden = false;
    }
  });
})();
