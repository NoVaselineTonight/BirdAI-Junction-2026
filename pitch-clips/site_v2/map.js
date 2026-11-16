/* Feeder Census demo: the "implications" view. Map, controls, headline numbers, and two containers
   that charts.js fills (FC.charts.renderStation / FC.charts.renderNetwork). All data is simulated. */
(function () {
  'use strict';
  var FC = (window.FC = window.FC || {});
  var SVGNS = 'http://www.w3.org/2000/svg';

  function h(tag, attrs, children) {
    var e = document.createElement(tag);
    setup(e, attrs, children);
    return e;
  }
  function s(tag, attrs, children) {
    var e = document.createElementNS(SVGNS, tag);
    setup(e, attrs, children);
    return e;
  }
  function setup(e, attrs, children) {
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'text') e.textContent = v;
        else e.setAttribute(k, v === true ? '' : v);
      });
    }
    (children || []).forEach(function (c) { if (c) e.appendChild(c); });
  }

  FC.mountMap = function (el) {
    var D = FC.data;
    var stations = D.stations, species = D.species, periods = D.periods;
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var home = stations.filter(function (st) { return st.name === 'Haukipudas'; })[0] || stations[0];
    var state = { species: 'all', period: 8, stationId: home ? home.id : null };

    // ---- map geometry (viewBox units) ----
    var W = 480, H = Math.round(W / FC.mapAspect);
    var R_MIN = 3.5, R_MAX = 17;
    function px(lon, lat) { var p = FC.project(lon, lat); return { x: p.x * W, y: p.y * H }; }

    // Fixed scale per species choice so dots are comparable across periods.
    var maxCache = {};
    function maxFor(sp) {
      if (maxCache[sp] !== undefined) return maxCache[sp];
      var m = 1;
      stations.forEach(function (st) {
        for (var p = 0; p < periods.length; p++) {
          var v = countFor(st, p, sp);
          if (v > m) m = v;
        }
      });
      maxCache[sp] = m;
      return m;
    }
    function countFor(st, p, sp) {
      return sp === 'all' ? FC.util.stationTotal(st, p) : st.counts[sp][p];
    }
    function radius(v, sp) {
      if (v <= 0) return 3.2;
      return R_MIN + (R_MAX - R_MIN) * Math.sqrt(v / maxFor(sp));
    }
    function dotColor() {
      return state.species === 'all' ? 'var(--sci)' : FC.util.speciesById(state.species).color;
    }
    function speciesLabel() {
      return state.species === 'all' ? 'all species' : FC.util.speciesById(state.species).name;
    }

    // ---- build DOM ----
    el.textContent = '';
    var root = h('div', { 'class': 'map-view' });
    el.appendChild(root);

    var uid = 'mv' + Math.floor(Math.random() * 1e6);

    // stats
    var statEls = {};
    function stat(key, label) {
      var num = h('span', { 'class': 'mv-stat-num', text: '0' });
      statEls[key] = num;
      return h('div', { 'class': 'mv-stat' }, [num, h('span', { 'class': 'mv-stat-label', text: label })]);
    }
    var statsRow = h('div', { 'class': 'mv-stats', role: 'group', 'aria-label': 'Network totals for the chosen period' }, [
      stat('reporting', 'stations reporting'),
      stat('hours', 'hours watched'),
      stat('seen', 'stations that saw it'),
    ]);
    var statSeenLabel = statsRow.lastChild.lastChild;

    // species chips
    var chipWrap = h('div', { 'class': 'mv-chips', role: 'group', 'aria-label': 'Species' });
    var chips = {};
    function addChip(id, name, color) {
      var b = h('button', { type: 'button', 'class': 'mv-chip', 'aria-pressed': 'false', 'data-species': id }, [
        h('span', { 'class': 'mv-chip-sw', style: 'background:' + (color || 'var(--sci)') }),
        h('span', { text: name }),
      ]);
      b.addEventListener('click', function () { state.species = id; update(); });
      chips[id] = b;
      chipWrap.appendChild(b);
    }
    addChip('all', 'All species', null);
    species.forEach(function (sp) { addChip(sp.id, sp.name, sp.color); });

    // period controls
    var playBtn = h('button', { type: 'button', 'class': 'mv-play', 'aria-label': 'Play through the winter' , text: 'Play' });
    var periodLabel = h('output', { 'class': 'mv-period-label', 'for': uid + '-range', 'aria-live': 'polite' });
    var slider = h('input', {
      type: 'range', id: uid + '-range', 'class': 'mv-range', min: '0', max: String(periods.length - 1), step: '1',
      value: String(state.period), 'aria-label': 'Half-month period',
    });
    var scale = h('div', { 'class': 'mv-scale', 'aria-hidden': 'true' }, [
      h('span', { text: periods[0].label }), h('span', { text: periods[periods.length - 1].label }),
    ]);
    var periodRow = h('div', { 'class': 'mv-period' }, [
      h('div', { 'class': 'mv-period-top' }, [
        h('label', { 'class': 'mv-ctl-title', 'for': uid + '-range', text: 'Period' }), periodLabel, playBtn,
      ]),
      slider, scale,
    ]);

    // map
    var svg = s('svg', {
      'class': 'mv-svg', viewBox: '0 0 ' + W + ' ' + H, role: 'group',
      'aria-label': 'Map of Finland with simulated feeder stations',
      preserveAspectRatio: 'xMidYMid meet',
    });
    var path = D.outline.map(function (pt, i) {
      var p = px(pt[0], pt[1]);
      return (i ? 'L' : 'M') + p.x.toFixed(1) + ' ' + p.y.toFixed(1);
    }).join('') + 'Z';
    svg.appendChild(s('path', { 'class': 'mv-outline', d: path }));
    [[60, '60° N'], [65, '65° N'], [66.56, 'Arctic Circle'], [70, '70° N']].forEach(function (g) {
      var gy = px(20, g[0]).y.toFixed(1);
      svg.appendChild(s('line', { 'class': 'mv-grat' + (g[0] === 66.56 ? ' is-arctic' : ''), x1: 0, x2: W, y1: gy, y2: gy }));
      svg.appendChild(s('text', { 'class': 'mv-grat-t', x: 4, y: gy - 4, text: g[1] }));
    });
    var dotLayer = s('g', { 'class': 'mv-dots' });
    svg.appendChild(dotLayer);
    var selRing = s('circle', { 'class': 'mv-sel', r: '20', 'aria-hidden': 'true' });
    svg.appendChild(selRing);

    var dots = {}; // id -> {g, c}
    function addDot(st) {
      var p = px(st.lon, st.lat);
      var c = s('circle', { 'class': 'mv-dot', cx: p.x.toFixed(1), cy: p.y.toFixed(1), r: '4' });
      var hit = s('circle', { 'class': 'mv-hit', cx: p.x.toFixed(1), cy: p.y.toFixed(1), r: '14' });
      var g = s('g', { 'class': 'mv-st', tabindex: '0', role: 'button', 'data-id': st.id }, [hit, c]);
      g.addEventListener('mouseenter', function () { showTip(st); });
      g.addEventListener('mousemove', function (e) { moveTip(e); });
      g.addEventListener('mouseleave', hideTip);
      g.addEventListener('focus', function () { showTip(st, true); });
      g.addEventListener('blur', hideTip);
      g.addEventListener('click', function () { select(st.id); });
      g.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); select(st.id); }
      });
      dots[st.id] = { g: g, c: c, x: p.x, y: p.y, st: st };
      dotLayer.appendChild(g);
    }
    stations.forEach(addDot);

    // place your own feeder
    var placing = false, placed = 0;
    var placeBtn = h('button', { type: 'button', 'class': 'mv-play mv-place', 'aria-pressed': 'false', text: 'Place your own feeder' });
    var habitatSel = h('select', { 'class': 'mv-select', 'aria-label': 'Habitat of your feeder' }, [
      h('option', { value: 'forest', text: 'in a forest' }), h('option', { value: 'farmland', text: 'on farmland' }), h('option', { value: 'town', text: 'in a town' }),
    ]);
    var placeMsg = h('span', { 'class': 'mv-place-msg', role: 'status' });
    function setPlacing(on) {
      placing = on;
      placeBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
      placeBtn.textContent = on ? 'Now click the map' : 'Place your own feeder';
      svg.classList.toggle('is-placing', on);
    }
    placeBtn.addEventListener('click', function () { placeMsg.textContent = ''; setPlacing(!placing); });
    svg.addEventListener('click', function (e) {
      if (!placing || (e.target.closest && e.target.closest('.mv-st'))) return;
      var r = svg.getBoundingClientRect();
      var ll = FC.unproject((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
      if (!FC.insideOutline(ll.lon, ll.lat)) { placeMsg.textContent = 'That is outside Finland. Click inside the outline.'; return; }
      placed++;
      var st = FC.makeStation('Your feeder' + (placed > 1 ? ' ' + placed : ''), ll.lat, ll.lon, habitatSel.value, 500 + placed * 13 + Math.round(ll.lat * 10), 'u' + placed);
      stations.push(st);
      maxCache = {};
      addDot(st);
      dots[st.id].g.classList.add('is-yours');
      placeMsg.textContent = st.name + ' is at ' + ll.lat.toFixed(1) + '° N. We simulated its counts for that latitude and habitat.';
      setPlacing(false);
      select(st.id);
    });

    var tip = h('div', { 'class': 'mv-tip', role: 'status', hidden: true });
    var mapBox = h('div', { 'class': 'mv-mapbox', style: '--mv-aspect:' + (W / H).toFixed(4) }, [svg, tip]);

    // legend
    function legendDot(r, hollow) {
      var d = r * 2 + 4;
      var sv = s('svg', { width: d, height: d, viewBox: '0 0 ' + d + ' ' + d, 'aria-hidden': 'true' });
      sv.appendChild(s('circle', { cx: d / 2, cy: d / 2, r: r, 'class': hollow ? 'mv-lg-ring' : 'mv-lg-dot' }));
      return sv;
    }
    var legMaxText = h('span', { text: '' });
    var legend = h('div', { 'class': 'mv-legend' }, [
      h('span', { 'class': 'mv-lg' }, [legendDot(R_MIN + 1, false), h('span', { text: 'few' }),
        legendDot(R_MAX * 0.7, false), h('span', { text: 'many birds at once' })]),
      h('span', { 'class': 'mv-lg' }, [legendDot(3.2, true), h('span', { text: 'watched, none seen' })]),
    ]);
    var legNote = h('p', { 'class': 'mv-note', text: 'A bigger dot means more birds seen at once, the number the national count records.' });
    var simNote = h('p', { 'class': 'mv-note', text: 'The stations and counts are simulated. The outline of Finland is simplified.' });

    var left = h('div', { 'class': 'mv-left' }, [
      statsRow,
      h('div', { 'class': 'mv-card mv-controls' }, [
        h('div', { 'class': 'mv-ctl' }, [h('span', { 'class': 'mv-ctl-title', text: 'Species' }), chipWrap]),
        periodRow,
      ]),
      h('div', { 'class': 'mv-card mv-mapcard' }, [
        h('div', { 'class': 'mv-placebar' }, [placeBtn, habitatSel, placeMsg]), mapBox, legend, legNote, simNote]),
    ]);

    var stationEl = h('div', { 'class': 'mv-station', id: uid + '-station' });
    var networkEl = h('div', { 'class': 'mv-network', id: uid + '-network' });
    var minutes = h('input', { type: 'range', id: uid + '-min', 'class': 'mv-range', min: '0', max: '120', step: '5', value: '15' });
    var minutesOut = h('output', { 'class': 'mv-period-label', 'for': uid + '-min' });
    var coverEl = h('div', { 'class': 'mv-cover' });
    var coverCard = h('div', { 'class': 'mv-card mv-covercard' }, [
      h('h3', { 'class': 'mv-h3', text: 'How long a person and a device can watch' }),
      h('div', { 'class': 'mv-period-top' }, [h('label', { 'class': 'mv-ctl-title', 'for': uid + '-min', text: 'A person watches' }), minutesOut]),
      minutes, coverEl,
    ]);
    minutes.addEventListener('input', function () { renderCover(selectedStation()); });
    function renderCover(sel) {
      minutesOut.textContent = minutes.value + ' min a day';
      if (FC.charts && FC.charts.renderCoverage) FC.charts.renderCoverage(coverEl, sel || home, parseInt(minutes.value, 10));
    }
    var right = h('div', { 'class': 'mv-right' }, [stationEl, coverCard, networkEl]);

    root.appendChild(left);
    root.appendChild(right);

    // ---- tooltip ----
    function showTip(st, fromFocus) {
      var v = countFor(st, state.period, state.species);
      tip.textContent = '';
      tip.appendChild(h('strong', { text: st.name }));
      tip.appendChild(h('span', { text: st.habitat + ' feeder' }));
      tip.appendChild(h('span', { text: (v === 0 ? 'None seen' : v + ' ' + (state.species === 'all' ? 'birds' : speciesLabel().toLowerCase())) +
        ' in ' + st.hours[state.period] + ' h watched' }));
      tip.hidden = false;
      tip.dataset.id = st.id;
      if (fromFocus) positionTipAt(dots[st.id].x, dots[st.id].y);
    }
    function positionTipAt(vx, vy) {
      var r = svg.getBoundingClientRect(), b = mapBox.getBoundingClientRect();
      var k = r.width / W;
      place(r.left - b.left + vx * k, r.top - b.top + vy * k - 14);
    }
    function moveTip(e) {
      var b = mapBox.getBoundingClientRect();
      place(e.clientX - b.left, e.clientY - b.top - 14);
    }
    function place(x, y) {
      var bw = mapBox.clientWidth, tw = tip.offsetWidth, th = tip.offsetHeight;
      var left = Math.max(4, Math.min(bw - tw - 4, x - tw / 2));
      var top = y - th;
      if (top < 4) top = y + 34;
      tip.style.left = left + 'px';
      tip.style.top = top + 'px';
    }
    function hideTip() { tip.hidden = true; }

    // ---- state ----
    function select(id) {
      state.stationId = id;
      update();
    }
    function selectedStation() {
      return stations.filter(function (st) { return st.id === state.stationId; })[0] || null;
    }

    function update() {
      var sp = state.species, p = state.period;
      Object.keys(chips).forEach(function (id) { chips[id].setAttribute('aria-pressed', id === sp ? 'true' : 'false'); });
      periodLabel.textContent = periods[p].label;
      slider.value = String(p);
      slider.setAttribute('aria-valuetext', periods[p].label);

      var reporting = 0, hours = 0, seen = 0;
      var col = dotColor();
      svg.style.setProperty('--mv-dot', col);
      stations.forEach(function (st) {
        var v = countFor(st, p, sp), d = dots[st.id];
        if (st.hours[p] > 0) reporting++;
        hours += st.hours[p];
        if (v > 0) seen++;
        d.c.setAttribute('r', radius(v, sp).toFixed(1));
        d.c.setAttribute('class', 'mv-dot' + (v === 0 ? ' is-zero' : ''));
        d.g.setAttribute('aria-label', st.name + ', ' + st.habitat + ', ' +
          (v === 0 ? 'none seen' : v + ' ' + speciesLabel()) + ', ' + st.hours[p] + ' hours watched, ' + periods[p].label);
        d.g.setAttribute('aria-pressed', st.id === state.stationId ? 'true' : 'false');
      });
      statEls.reporting.textContent = reporting + ' / ' + stations.length;
      statEls.hours.textContent = hours.toLocaleString('en');
      statEls.seen.textContent = seen + ' / ' + stations.length;
      statSeenLabel.textContent = sp === 'all' ? 'stations that saw any bird' : 'stations that saw ' + speciesLabel().toLowerCase();

      var sel = selectedStation();
      if (sel) {
        var dd = dots[sel.id];
        selRing.setAttribute('cx', dd.x.toFixed(1));
        selRing.setAttribute('cy', dd.y.toFixed(1));
        selRing.setAttribute('r', (parseFloat(dd.c.getAttribute('r')) + 5).toFixed(1));
        selRing.style.display = '';
      } else {
        selRing.style.display = 'none';
      }
      if (!tip.hidden && tip.dataset.id) {
        var ts = stations.filter(function (x) { return x.id === tip.dataset.id; })[0];
        if (ts) showTip(ts);
      }
      render(sel);
    }

    function render(sel) {
      renderCover(sel);
      if (FC.charts && FC.charts.renderStation) {
        FC.charts.renderStation(stationEl, sel, state);
      } else {
        stationEl.textContent = '';
        stationEl.appendChild(h('p', { 'class': 'mv-fallback',
          text: sel ? sel.name + ' (' + sel.habitat + '): charts are not loaded.' : 'Select a station on the map.' }));
      }
      if (FC.charts && FC.charts.renderNetwork) {
        FC.charts.renderNetwork(networkEl, state);
      } else {
        networkEl.textContent = '';
        networkEl.appendChild(h('p', { 'class': 'mv-fallback', text: 'Network charts are not loaded.' }));
      }
    }

    // ---- events ----
    slider.addEventListener('input', function () {
      state.period = parseInt(slider.value, 10);
      update();
    });

    var timer = null;
    function setPlaying(on) {
      if (on && !timer) {
        timer = setInterval(function () {
          state.period = (state.period + 1) % periods.length;
          update();
        }, 1000);
      } else if (!on && timer) {
        clearInterval(timer);
        timer = null;
      }
      playBtn.textContent = timer ? 'Pause' : 'Play';
      playBtn.setAttribute('aria-label', timer ? 'Pause' : 'Play through the winter');
      playBtn.classList.toggle('is-on', !!timer);
    }
    playBtn.addEventListener('click', function () { setPlaying(!timer); });
    // stop the loop when the view is hidden (the page switches views with the hidden attribute)
    setInterval(function () { if (timer && !root.offsetParent) setPlaying(false); }, 1500);
    // Keep an open tooltip aligned if the viewport changes.
    window.addEventListener('resize', hideTip);

    void reduceMotion; // Play is never started automatically, so nothing animates unless the visitor asks.
    update();
  };
})();
