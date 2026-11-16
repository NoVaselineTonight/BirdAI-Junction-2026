/* Feeder Census demo: station and network charts. Plain script, no libraries. Data is simulated. */
(function () {
  const FC = (window.FC = window.FC || {});
  const D = () => FC.data;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function rgba(hex, a) {
    const h = hex.replace('#', '');
    const n = parseInt(h.length === 3 ? h.replace(/./g, '$&$&') : h, 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a.toFixed(2) + ')';
  }
  function fmt(v) {
    return (Math.round(v * 10) / 10).toLocaleString('en-US', { maximumFractionDigits: 1 });
  }
  function periodOf(state) {
    const p = state && Number.isInteger(state.period) ? state.period : 0;
    return Math.max(0, Math.min(D().periods.length - 1, p));
  }
  function speciesOf(state) {
    return state && state.species && state.species !== 'all' ? FC.util.speciesById(state.species) || null : null;
  }

  const GROUP_LABEL = { forest: 'Forest', town: 'Town', generalist: 'Generalist' };
  const GROUP_COLOR = { forest: 'var(--tech)', town: 'var(--sci)', generalist: 'var(--muted)' };

  function groupShares(valueFn, period) {
    const tot = { forest: 0, town: 0, generalist: 0 };
    D().species.forEach((sp) => { tot[sp.group] += valueFn(sp.id, period); });
    const sum = tot.forest + tot.town + tot.generalist;
    return { tot, sum };
  }

  function stackedBar(label, shares) {
    const { tot, sum } = shares;
    let segs = '';
    if (sum > 0) {
      D().groups.forEach((g) => {
        const pct = (tot[g] / sum) * 100;
        if (pct <= 0) return;
        segs += '<span class="fcc-seg" style="width:' + pct.toFixed(2) + '%;background:' + GROUP_COLOR[g] + '" title="' +
          GROUP_LABEL[g] + ': ' + Math.round(pct) + '%">' + (pct >= 12 ? Math.round(pct) + '%' : '') + '</span>';
      });
    } else {
      segs = '<span class="fcc-seg-empty">No birds counted</span>';
    }
    return '<div class="fcc-barrow"><div class="fcc-barlabel">' + esc(label) + '</div><div class="fcc-stack" role="img" aria-label="' +
      esc(label) + ' habitat mix">' + segs + '</div></div>';
  }

  function stationHeader(st, p) {
    const per = D().periods[p];
    return '<div class="fcc-head"><div><h3>' + esc(st.name) + '</h3><p class="fcc-sub">' + esc(st.habitat) + ' habitat</p></div>' +
      '<dl class="fcc-stats"><div><dt>Period</dt><dd>' + esc(per.label) + '</dd></div>' +
      '<div><dt>Hours watched</dt><dd>' + st.hours[p] + '</dd></div>' +
      '<div><dt>Species seen</dt><dd>' + FC.util.stationSpeciesCount(st, p) + ' of ' + D().species.length + '</dd></div></dl></div>';
  }

  function heatTable(st, state, p) {
    const sps = D().species, pers = D().periods;
    let max = 1;
    sps.forEach((sp) => st.counts[sp.id].forEach((v) => { if (v > max) max = v; }));
    const selId = speciesOf(state) ? state.species : null;
    let h = '<div class="fcc-tablewrap"><table class="fcc-heat"><caption class="fcc-cap">Largest number seen at once, by half-month period</caption><thead><tr><th class="fcc-sp" scope="col">Species</th>';
    pers.forEach((per, i) => {
      h += '<th scope="col" class="' + (i === p ? 'fcc-cur' : '') + '" title="' + esc(per.label) + '">' + esc(per.short.replace(' ', ' ')) + '</th>';
    });
    h += '</tr></thead><tbody>';
    sps.forEach((sp) => {
      const sel = sp.id === selId;
      h += '<tr class="' + (sel ? 'fcc-selrow' : '') + '"><th scope="row" class="fcc-sp"><span class="fcc-dot" style="background:' + sp.color + '"></span><span class="fcc-spn">' +
        esc(sp.name) + '<small>' + esc(sp.fi) + '</small></span></th>';
      st.counts[sp.id].forEach((v, i) => {
        const a = v > 0 ? 0.18 + 0.72 * Math.sqrt(v / max) : 0;
        h += '<td class="' + (i === p ? 'fcc-cur' : '') + (v === 0 ? ' fcc-zero' : '') + '"' +
          (v > 0 ? ' style="background:' + rgba(sp.color, a) + '"' : '') + '>' + v + '</td>';
      });
      h += '</tr>';
    });
    return h + '</tbody></table></div>';
  }

  function renderStation(el, station, state) {
    if (!station) {
      el.innerHTML = '<div class="fc-charts"><section class="fcc-card"><h3>What one feeder reports</h3>' +
        '<p class="fcc-empty">Select a feeder on the map to see the counts it would report.</p></section></div>';
      return;
    }
    const p = periodOf(state);
    const net = stackedBar('Network average', groupShares((id, per) => FC.util.networkMean(id, per), p));
    const own = stackedBar(station.name, groupShares((id, per) => station.counts[id][per], p));
    const legend = D().groups.map((g) =>
      '<li><span class="fcc-key" style="background:' + GROUP_COLOR[g] + '"></span>' + GROUP_LABEL[g] + '</li>').join('');
    el.innerHTML = '<div class="fc-charts"><section class="fcc-card">' + stationHeader(station, p) +
      '<h4>What the feeder reports, October to April</h4>' + heatTable(station, state, p) +
      '<p class="fcc-note">Each cell is the largest number of that species seen at once in the period. A 0 means the feeder was watched and none came.</p>' +
      '<h4>Habitat mix, ' + esc(D().periods[p].label) + '</h4>' + own + net +
      '<ul class="fcc-legend">' + legend + '</ul>' +
      '<p class="fcc-note">The habitat groups are our own. We have not checked them with Luomus.</p></section></div>';
  }

  function niceMax(v) {
    if (v <= 0) return 1;
    const pow = Math.pow(10, Math.floor(Math.log10(v)));
    const f = v / pow;
    const n = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    return n * pow;
  }

  function curve(state, p) {
    const sp = speciesOf(state);
    const n = D().periods.length;
    const vals = [];
    for (let i = 0; i < n; i++) {
      vals.push(sp ? FC.util.networkMean(sp.id, i)
        : D().species.reduce((a, s) => a + FC.util.networkMean(s.id, i), 0));
    }
    const top = niceMax(Math.max.apply(null, vals));
    const W = 400, H = 200, L = 34, R = 12, T = 18, B = 26;
    const x = (i) => L + ((W - L - R) * i) / (n - 1);
    const y = (v) => T + (H - T - B) * (1 - v / top);
    const col = sp ? sp.color : 'var(--sci)';
    let s = '<svg class="fcc-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Network mean count by period">';
    [0, top / 2, top].forEach((t) => {
      s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(t) + '" y2="' + y(t) + '" class="fcc-grid"/>' +
        '<text x="' + (L - 6) + '" y="' + (y(t) + 4) + '" class="fcc-tick" text-anchor="end">' + fmt(t) + '</text>';
    });
    D().periods.forEach((per, i) => {
      if (i % 2 === 0) s += '<text x="' + ((x(i) + x(i + 1)) / 2) + '" y="' + (H - 8) + '" class="fcc-tick" text-anchor="middle">' + esc(per.month) + '</text>';
    });
    const pts = vals.map((v, i) => x(i).toFixed(1) + ',' + y(v).toFixed(1));
    s += '<polygon points="' + x(0).toFixed(1) + ',' + y(0) + ' ' + pts.join(' ') + ' ' + x(n - 1).toFixed(1) + ',' + y(0) + '" fill="' + col + '" opacity="0.16"/>';
    s += '<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + col + '" stroke-width="2" stroke-linejoin="round"/>';
    const cx = x(p), cy = y(vals[p]);
    s += '<line x1="' + cx + '" x2="' + cx + '" y1="' + T + '" y2="' + y(0) + '" class="fcc-marker"/>';
    s += '<circle cx="' + cx + '" cy="' + cy + '" r="5" fill="' + col + '" stroke="var(--bg)" stroke-width="2"/>';
    const anchor = cx > W - 60 ? 'end' : cx < L + 40 ? 'start' : 'middle';
    s += '<text x="' + cx + '" y="' + Math.max(12, cy - 10) + '" class="fcc-val" text-anchor="' + anchor + '">' + fmt(vals[p]) + '</text>';
    return { svg: s + '</svg>', value: vals[p] };
  }

  function ranked(state, p) {
    const sp = speciesOf(state);
    const rows = D().stations.map((st) => ({
      st, v: sp ? st.counts[sp.id][p] : FC.util.stationTotal(st, p),
    })).sort((a, b) => b.v - a.v || a.st.name.localeCompare(b.st.name)).slice(0, 8);
    const max = Math.max(1, rows[0] ? rows[0].v : 1);
    const col = sp ? sp.color : 'var(--sci)';
    return '<ol class="fcc-rank">' + rows.map((r) =>
      '<li class="' + (state && r.st.id === state.stationId ? 'fcc-selst' : '') + '"><span class="fcc-rn">' + esc(r.st.name) +
      '</span><span class="fcc-rtrack"><span class="fcc-rbar" style="width:' + ((r.v / max) * 100).toFixed(1) + '%;background:' + col + '"></span></span>' +
      '<span class="fcc-rv">' + r.v + '</span></li>').join('') + '</ol>';
  }

  function renderNetwork(el, state) {
    const p = periodOf(state);
    const sp = speciesOf(state);
    const what = sp ? sp.name : 'all species';
    const c = curve(state, p);
    el.innerHTML = '<div class="fc-charts"><section class="fcc-card">' +
      '<h3>Birds per feeder through the winter</h3>' +
      '<p class="fcc-sub">Winter curve: mean count per station, ' + esc(what) + '</p>' + c.svg +
      '<h4>Where it is seen, ' + esc(D().periods[p].label) + '</h4>' +
      '<p class="fcc-sub">Top 8 stations, ' + (sp ? 'largest number of ' + esc(sp.name.toLowerCase()) + ' at once' : 'total birds counted') + '</p>' + ranked(state, p) +
      '<p class="fcc-why">Every feeder counts by the same rule, so the counts can be compared and combined into a trend. Repeated over many winters, that trend is the kind of indicator the EU already uses to judge its environmental policy.</p>' +
      '<p class="fcc-note">This data is simulated. One feeder is one data point, and a count at a feeder is not the number of birds in the area.</p></section></div>';
  }

  // Hours watched per half-month: every daylight hour (the device) against a fixed daily session (a person).
  function renderCoverage(el, st, minutes) {
    const pers = D().periods;
    const top = Math.max.apply(null, st.hours.concat([1]));
    let dev = 0, hum = 0, cols = '';
    pers.forEach((per, i) => {
      const d = st.hours[i], hh = Math.min(d, (minutes / 60) * per.days);
      dev += d; hum += hh;
      cols += '<div class="fcc-cov-col" title="' + esc(per.label) + ': device ' + d + ' h, person ' + fmt(hh) + ' h">' +
        '<div class="fcc-cov-bars"><span class="fcc-cov-d" style="height:' + ((d / top) * 100).toFixed(1) + '%"></span><span class="fcc-cov-h" style="height:' + ((hh / top) * 100).toFixed(1) + '%"></span></div>' +
        '<small>' + (i % 2 === 0 ? esc(per.month) : '') + '</small></div>';
    });
    const ratio = hum > 0 ? dev / hum : 0;
    el.innerHTML = '<div class="fc-charts"><div class="fcc-cov" role="img" aria-label="Hours watched per half-month at ' + esc(st.name) + '">' + cols + '</div>' +
      '<ul class="fcc-legend"><li><span class="fcc-key" style="background:var(--sci)"></span>Device: every daylight hour, ' + fmt(dev) + ' h</li>' +
      '<li><span class="fcc-key" style="background:var(--sun)"></span>Person: ' + fmt(hum) + ' h</li></ul>' +
      '<p class="fcc-why">' + (hum > 0 ? 'At ' + esc(st.name) + ' the device watches about ' + fmt(ratio) + ' times as long over the winter. ' : 'Nobody watching means no count at all. ') +
      'The census count is the largest number seen at once, so the only way to miss it is to not be looking. Short sessions tend to undercount.</p>' +
      '<p class="fcc-note">Daylight is computed from the latitude of ' + esc(st.name) + '. You set the person\'s minutes yourself. They are not a Luomus figure.</p></div>';
  }

  FC.charts = { renderStation: renderStation, renderNetwork: renderNetwork, renderCoverage: renderCoverage };
})();
