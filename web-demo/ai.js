/* Feeder Census demo: "Explore the AI" view. Plain script, no libraries, no network.
   Defines FC.mountAI(el). The loop simulator is scripted; the numbers come from FC.facts. */
(function () {
  const FC = (window.FC = window.FC || {});

  const SPECIES = {
    great_tit: { name: 'Great tit', color: '#C99700' },
    blue_tit: { name: 'Blue tit', color: '#3E7FC1' },
    bullfinch: { name: 'Bullfinch', color: '#C8553F' },
    willow_tit: { name: 'Willow tit', color: '#8C7A62' },
    tree_sparrow: { name: 'Tree sparrow', color: '#B5722E' },
    squirrel: { name: 'Red squirrel', color: '#C4622D' },
  };
  const BIRD_KEYS = ['great_tit', 'blue_tit', 'bullfinch', 'willow_tit', 'tree_sparrow'];

  // One entry per photo. id = the same physical bird across photos. d = facing (1 right, -1 left).
  function b(id, sp, conf, x, y, d) { return { id: id, sp: sp, conf: conf, x: x, y: y, d: d || 1 }; }
  const SCRIPT = [
    /* 1 */ [b('a', 'great_tit', 0.91, 160, 160)],
    /* 2 */ [b('a', 'great_tit', 0.93, 165, 165), b('b', 'blue_tit', 0.84, 470, 150, -1)],
    /* 3 */ [b('a', 'great_tit', 0.9, 170, 160), b('b', 'blue_tit', 0.88, 465, 155, -1), b('c', 'bullfinch', 0.46, 310, 300)],
    /* 4 */ [b('a', 'great_tit', 0.92, 160, 170), b('b', 'blue_tit', 0.86, 470, 150, -1), b('c', 'bullfinch', 0.71, 312, 302)],
    /* 5 */ [b('a', 'great_tit', 0.9, 155, 165), b('c', 'bullfinch', 0.78, 310, 300), b('f', 'great_tit', 0.88, 500, 270, -1)],
    /* 6 */ [b('a', 'great_tit', 0.9, 160, 160), b('c', 'bullfinch', 0.8, 315, 298), b('f', 'great_tit', 0.9, 505, 272, -1)],
    /* 7 */ [b('c', 'bullfinch', 0.79, 310, 300), b('f', 'great_tit', 0.89, 500, 270, -1), b('d', 'willow_tit', 0.62, 150, 290)],
    /* 8 */ [b('f', 'great_tit', 0.9, 500, 270, -1), b('d', 'willow_tit', 0.66, 150, 292), b('q', 'squirrel', 0.94, 330, 170), b('e', 'tree_sparrow', 0.38, 560, 345, -1)],
    /* 9 */ [b('f', 'great_tit', 0.9, 502, 270, -1), b('d', 'willow_tit', 0.68, 150, 292), b('q', 'squirrel', 0.96, 335, 175), b('e', 'tree_sparrow', 0.55, 560, 345, -1)],
    /* 10 */ [b('d', 'willow_tit', 0.7, 150, 290), b('q', 'squirrel', 0.9, 340, 180), b('e', 'tree_sparrow', 0.6, 558, 345, -1)],
    /* 11 */ [b('d', 'willow_tit', 0.67, 150, 290), b('e', 'tree_sparrow', 0.62, 560, 345, -1), b('g', 'blue_tit', 0.81, 130, 135)],
    /* 12 */ [b('e', 'tree_sparrow', 0.7, 560, 345, -1), b('g', 'blue_tit', 0.85, 135, 140), b('h', 'great_tit', 0.87, 410, 160, -1)],
    /* 13 */ [b('e', 'tree_sparrow', 0.69, 558, 340, -1), b('g', 'blue_tit', 0.86, 130, 140), b('h', 'great_tit', 0.9, 405, 165, -1)],
    /* 14 */ [b('e', 'tree_sparrow', 0.71, 560, 345, -1), b('g', 'blue_tit', 0.88, 135, 138), b('h', 'great_tit', 0.9, 410, 160, -1)],
    /* 15 */ [b('e', 'tree_sparrow', 0.7, 560, 345, -1), b('g', 'blue_tit', 0.87, 130, 140), b('h', 'great_tit', 0.91, 405, 165, -1)],
    /* 16 */ [b('e', 'tree_sparrow', 0.72, 558, 342, -1), b('h', 'great_tit', 0.9, 410, 160, -1)],
    /* 17 */ [b('e', 'tree_sparrow', 0.73, 560, 345, -1), b('h', 'great_tit', 0.9, 405, 162, -1), b('j', 'tree_sparrow', 0.72, 220, 335)],
    /* 18 */ [b('e', 'tree_sparrow', 0.7, 560, 345, -1), b('h', 'great_tit', 0.89, 410, 160, -1), b('j', 'tree_sparrow', 0.75, 222, 335)],
    /* 19 */ [b('h', 'great_tit', 0.9, 405, 165, -1), b('j', 'tree_sparrow', 0.74, 220, 338)],
    /* 20 */ [],
  ];

  const STEPS = ['Photo', 'Detect', 'Filter', 'Confirm', 'Record', 'Latch'];
  const TICK_MS = 1400;

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fmt(n) { return Number(n).toLocaleString('en-US'); }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

  FC.mountAI = function (el) {
    const F = Object.assign({
      msPerPhoto: 507, budgetMs: 1500, photoEveryS: 5, modelMB: 10, classes: 13, countThreshold: 0.5,
      testFrames: 899, testDay: '12 November 2026', countedRight: 0.84, trainingDays: 25, trainingFrames: 62185,
      labelledBoxes: 88466, latchCloseAfter: 2, latchOpenAfter: 5, failsafeS: 30,
    }, FC.facts || {});
    const reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const N = SCRIPT.length;
    const perHour = Math.round(3600 / F.photoEveryS);
    const secPhoto = (F.msPerPhoto / 1000).toFixed(1);
    const secBudget = (F.budgetMs / 1000).toFixed(1);
    const thr = F.countThreshold.toFixed(2);

    el.innerHTML =
      '<div class="ai-view">' +
      // 1. simulator
      '<section class="ai-sim" aria-labelledby="ai-sim-h">' +
        '<div class="ai-sec-head"><h2 id="ai-sim-h">The loop, step by step</h2>' +
        '<p class="ai-sim-note">Simulation of the loop. Not live video from the device.</p></div>' +
        '<p class="ai-lead">Every ' + F.photoEveryS + ' seconds the board takes a photo and runs the same six steps. Here one photo every ' + (TICK_MS / 1000).toFixed(1) + ' seconds stands for one photo every ' + F.photoEveryS + ' seconds on the device.</p>' +
        '<div class="ai-grid">' +
          '<div class="ai-stage">' +
            '<div class="ai-stage-bar"><span class="ai-photo-no" data-photo-no></span><span class="ai-device-time" data-device-time></span></div>' +
            '<div class="ai-tray" data-tray><svg viewBox="0 0 640 420" role="img" aria-label="Simulated top-down view of the feeding tray with detection boxes" data-svg></svg></div>' +
            '<div class="ai-controls" role="group" aria-label="Simulation controls">' +
              '<button type="button" class="ai-btn ai-btn-primary" data-play></button>' +
              '<button type="button" class="ai-btn" data-step>Step</button>' +
              '<button type="button" class="ai-btn" data-restart>Restart</button>' +
            '</div>' +
            '<h3 class="ai-h3">Found in this photo</h3>' +
            '<ul class="ai-dets" data-dets></ul>' +
          '</div>' +
          '<div class="ai-panel">' +
            '<div class="ai-latch" data-latch><p class="ai-latch-label">Squirrel latch</p><p class="ai-latch-state" data-latch-state></p><p class="ai-latch-why" data-latch-why></p></div>' +
            '<div class="ai-card">' +
              '<h3 class="ai-h3">Counts this hour</h3>' +
              '<div class="ai-table-wrap"><table class="ai-table"><thead><tr><th scope="col">Species</th><th scope="col" class="ai-num">In frame now</th><th scope="col" class="ai-num">Largest at once</th></tr></thead><tbody data-table></tbody></table></div>' +
              '<p class="ai-small">The count for a species is the largest number seen at once, so a bird that stays for ten photos is still one bird.</p>' +
            '</div>' +
            '<div class="ai-card">' +
              '<h3 class="ai-h3">Rules the device applies</h3>' +
              '<ul class="ai-rules">' +
                '<li>A name with confidence under ' + thr + ' is shown as unidentified and is not counted.</li>' +
                '<li>A bird is counted only when it is seen in ' + F.latchCloseAfter + ' photos in a row.</li>' +
                '<li>A red squirrel is never counted as a bird. Seen in ' + F.latchCloseAfter + ' photos in a row, it closes the latch. After ' + F.latchOpenAfter + ' photos in a row without it, the latch opens.</li>' +
              '</ul>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<h3 class="ai-h3 ai-h3-gap">What happens to each photo</h3>' +
        '<ol class="ai-steps" data-steps></ol>' +
        '<div class="ai-timing" data-timing>' +
          '<h3 class="ai-h3">Time budget for one photo</h3>' +
          '<div class="ai-bar" role="img" aria-label="Detector uses about ' + secPhoto + ' seconds of each ' + F.photoEveryS + ' seconds. Budget is ' + secBudget + ' seconds.">' +
            '<span class="ai-bar-use" data-bar-use style="width:' + (F.msPerPhoto / (F.photoEveryS * 10)).toFixed(2) + '%"></span>' +
            '<span class="ai-bar-budget" style="left:' + (F.budgetMs / (F.photoEveryS * 10)).toFixed(2) + '%"></span>' +
          '</div>' +
          '<ul class="ai-legend">' +
            '<li><span class="ai-key ai-key-use"></span>Detector: about ' + secPhoto + ' s per photo</li>' +
            '<li><span class="ai-key ai-key-budget"></span>Budget: ' + secBudget + ' s</li>' +
            '<li><span class="ai-key ai-key-rest"></span>Next photo at ' + F.photoEveryS + ' s</li>' +
          '</ul>' +
        '</div>' +
      '</section>' +
      // 2. measured numbers
      '<section aria-labelledby="ai-num-h">' +
        '<div class="ai-sec-head"><h2 id="ai-num-h">Measured numbers</h2></div>' +
        '<div class="ai-stats">' +
          '<div class="ai-stat"><p class="ai-stat-n">about ' + secPhoto + ' s</p><p class="ai-stat-t">per photo on the Arduino UNO Q, against a budget of ' + secBudget + ' s.</p></div>' +
          '<div class="ai-stat"><p class="ai-stat-n">' + F.modelMB + ' MB</p><p class="ai-stat-t">model with ' + F.classes + ' classes: 12 bird species and red squirrel.</p></div>' +
          '<div class="ai-stat"><p class="ai-stat-n">about ' + Math.round(F.countedRight * 100) + '%</p><p class="ai-stat-t">of roughly 1,600 birds counted under the right name on a held-out day (' + esc(F.testDay) + ', ' + fmt(F.testFrames) + ' frames).</p></div>' +
          '<div class="ai-stat"><p class="ai-stat-n">' + F.trainingDays + ' days</p><p class="ai-stat-t">of footage: ' + fmt(F.trainingFrames) + ' training frames and ' + fmt(F.labelledBoxes) + ' labelled boxes.</p></div>' +
        '</div>' +
      '</section>' +
      // 3. why edge
      '<section aria-labelledby="ai-edge-h">' +
        '<div class="ai-sec-head"><h2 id="ai-edge-h">Why it runs on the device</h2></div>' +
        '<div class="ai-cards">' +
          '<div class="ai-card"><h3>No connection needed</h3><p>The feeder works with no network. A feeder in a forest with no coverage counts the same as one in a town.</p></div>' +
          '<div class="ai-card"><h3>A table leaves, not video</h3><p>The board analyses ' + fmt(perHour) + ' photos an hour on the device. It keeps the counts and one evidence photo per species per day.</p></div>' +
          '<div class="ai-card"><h3>Open data, no company cloud</h3><p>The counts are a plain table that anyone can read. They do not pass through a vendor service.</p></div>' +
          '<div class="ai-card"><h3>Close enough to act</h3><p>The same board closes the latch. If commands stop, the microcontroller reopens it after ' + F.failsafeS + ' s.</p></div>' +
        '</div>' +
      '</section>' +
      // 4. videos
      '<section aria-labelledby="ai-vid-h">' +
        '<div class="ai-sec-head"><h2 id="ai-vid-h">Inside the build</h2></div>' +
        '<div class="ai-videos">' +
          '<figure><video src="clips/xray.mp4" autoplay muted loop playsinline aria-label="X-ray animation of the feeder"></video><figcaption>X-ray of the feeder: the board, the latch servo and what the camera sees.</figcaption></figure>' +
          '<figure><video src="clips/squirrel.mp4" autoplay muted loop playsinline aria-label="Animation of the camera cone turning red"></video><figcaption>The camera cone turns red when a squirrel is detected.</figcaption></figure>' +
        '</div>' +
        '<p class="ai-small">3D animations of our build, not footage from the device.</p>' +
      '</section>' +
      // 5. caveats
      '<section class="ai-caveats" aria-labelledby="ai-cav-h">' +
        '<h2 id="ai-cav-h">What these numbers do not say</h2>' +
        '<ul>' +
          '<li>The test day is the same feeder and camera as the training footage. A different feeder, light or background may do worse.</li>' +
          '<li>The truth labels are machine-made and spot-checked by a person. They are not a full hand count.</li>' +
          '<li>The model recognises red squirrels but has no rat class, so it cannot tell a rat from nothing.</li>' +
          '<li>The project demo plays recorded footage.</li>' +
        '</ul>' +
      '</section>' +
      '</div>';

    const $ = function (s) { return el.querySelector(s); };
    const svg = $('[data-svg]');
    const tray = $('[data-tray]');
    const stepsEl = $('[data-steps]');
    const playBtn = $('[data-play]');

    // pipeline strip skeleton
    stepsEl.innerHTML = STEPS.map(function (s, i) {
      return '<li class="ai-step" data-step-i="' + i + '"><span class="ai-step-n">' + (i + 1) + '</span><span class="ai-step-name">' + s + '</span><span class="ai-step-text" data-step-text></span></li>';
    }).join('');
    const stepNodes = stepsEl.querySelectorAll('.ai-step');
    const stepTexts = stepsEl.querySelectorAll('[data-step-text]');

    // simulation state
    let S, idx = -1, timer = null, stepTimers = [];
    function resetState() { S = { streak: {}, sq: 0, away: 0, latch: false, max: {}, now: {} }; BIRD_KEYS.forEach(function (k) { S.max[k] = 0; S.now[k] = 0; }); }
    resetState();

    function process(i) {
      const photo = SCRIPT[i];
      const present = {};
      const dets = photo.map(function (d) {
        present[d.id] = true;
        const r = { id: d.id, sp: d.sp, conf: d.conf, x: d.x, y: d.y, d: d.d };
        if (d.sp === 'squirrel') { r.status = 'squirrel'; return r; }
        if (d.conf < F.countThreshold) { S.streak[d.id] = 0; r.status = 'unidentified'; return r; }
        S.streak[d.id] = (S.streak[d.id] || 0) + 1;
        r.status = S.streak[d.id] >= 2 ? 'counted' : 'confirming';
        return r;
      });
      Object.keys(S.streak).forEach(function (id) { if (!present[id]) S.streak[id] = 0; });
      BIRD_KEYS.forEach(function (k) {
        S.now[k] = dets.filter(function (d) { return d.sp === k && d.status === 'counted'; }).length;
        if (S.now[k] > S.max[k]) S.max[k] = S.now[k];
      });
      const sqSeen = dets.some(function (d) { return d.sp === 'squirrel'; });
      let event = '';
      if (sqSeen) { S.sq++; S.away = 0; } else { S.sq = 0; S.away++; }
      if (!S.latch && S.sq >= F.latchCloseAfter) { S.latch = true; event = 'closed'; }
      else if (S.latch && S.away >= F.latchOpenAfter) { S.latch = false; event = 'opened'; }
      return { dets: dets, sqSeen: sqSeen, event: event };
    }

    // drawing
    function birdShape(d, grey) {
      const fill = grey ? 'var(--faint)' : SPECIES[d.sp].color;
      return '<g transform="translate(' + d.x + ' ' + d.y + ') scale(' + d.d + ' 1)" class="ai-shape" opacity="' + (grey ? 0.55 : 1) + '">' +
        '<rect x="-44" y="-5" width="26" height="9" rx="4" fill="' + fill + '" opacity="0.75"/>' +
        '<ellipse cx="0" cy="0" rx="30" ry="19" fill="' + fill + '"/>' +
        '<ellipse cx="-2" cy="2" rx="16" ry="9" fill="#000" opacity="0.14"/>' +
        '<circle cx="26" cy="-6" r="12" fill="' + fill + '"/>' +
        '<circle cx="30" cy="-9" r="2.4" fill="#151515"/>' +
        '<path d="M37 -7 L48 -4 L37 -1 Z" fill="#E8C07A"/>' +
        '</g>';
    }
    function squirrelShape(d) {
      const c = SPECIES.squirrel.color;
      return '<g transform="translate(' + d.x + ' ' + d.y + ')" class="ai-shape">' +
        '<ellipse cx="-46" cy="-14" rx="40" ry="17" fill="' + c + '" opacity="0.8" transform="rotate(-28 -46 -14)"/>' +
        '<ellipse cx="0" cy="0" rx="34" ry="21" fill="' + c + '"/>' +
        '<circle cx="34" cy="-5" r="14" fill="' + c + '"/>' +
        '<path d="M30 -17 L34 -29 L40 -16 Z" fill="' + c + '"/>' +
        '<circle cx="40" cy="-8" r="2.6" fill="#151515"/>' +
        '<ellipse cx="4" cy="6" rx="18" ry="8" fill="#F0D9BE" opacity="0.55"/>' +
        '</g>';
    }
    function statusText(s) { return { counted: 'counted', confirming: 'confirming', unidentified: 'unidentified', squirrel: 'not a bird' }[s]; }
    function boxColor(s) { return { counted: 'var(--tech)', confirming: 'var(--sci)', unidentified: 'var(--faint)', squirrel: 'var(--alert)' }[s]; }
    function detBox(d) {
      const sq = d.sp === 'squirrel';
      const w = sq ? 170 : 110, h = sq ? 110 : 84;
      const bx = d.x - w / 2 + (sq ? -4 : 0), by = d.y - h / 2;
      const name = d.status === 'unidentified' ? 'Unidentified' : SPECIES[d.sp].name;
      const l1 = name + ' ' + d.conf.toFixed(2);
      const l2 = statusText(d.status);
      const lw = Math.max(l1.length * 10.4, 100) + 16;
      const lx = Math.max(6, Math.min(bx, 634 - lw));
      const ly = Math.max(6, by - 46);
      const col = boxColor(d.status);
      return '<g class="ai-det">' +
        '<rect x="' + bx + '" y="' + by + '" width="' + w + '" height="' + h + '" rx="6" fill="none" stroke="' + col + '" stroke-width="3"' + (d.status === 'unidentified' ? ' stroke-dasharray="9 6"' : '') + '/>' +
        '<rect x="' + lx + '" y="' + ly + '" width="' + lw + '" height="42" rx="6" class="ai-lab-bg" stroke="' + col + '" stroke-width="2"/>' +
        '<text x="' + (lx + 8) + '" y="' + (ly + 18) + '" class="ai-lab-1">' + esc(l1) + '</text>' +
        '<text x="' + (lx + 8) + '" y="' + (ly + 36) + '" class="ai-lab-2" fill="' + col + '">' + esc(l2) + '</text>' +
        '</g>';
    }
    function drawTray(res) {
      let seeds = '';
      const pts = [[70, 60], [120, 380], [250, 90], [380, 360], [590, 80], [610, 230], [40, 220], [470, 60], [210, 230], [340, 250], [90, 330], [560, 400]];
      pts.forEach(function (p) { seeds += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="3" fill="#3D3226"/>'; });
      let shapes = '', boxes = '';
      res.dets.forEach(function (d) {
        shapes += d.sp === 'squirrel' ? squirrelShape(d) : birdShape(d, d.status === 'unidentified');
        boxes += detBox(d);
      });
      const edge = S.latch ? 'var(--alert)' : '#8A6844';
      svg.innerHTML =
        '<rect x="6" y="6" width="628" height="408" rx="30" fill="#C9A77A" stroke="' + edge + '" stroke-width="' + (S.latch ? 12 : 8) + '"/>' +
        '<rect x="26" y="26" width="588" height="368" rx="18" fill="#EFE9D8"/>' + seeds + shapes + boxes +
        (S.latch ? '<g><rect x="200" y="372" width="240" height="34" rx="17" fill="var(--alert)"/><text x="320" y="395" text-anchor="middle" class="ai-latch-txt">LATCH CLOSED</text></g>' : '');
      tray.classList.toggle('is-latched', S.latch);
    }

    function render(res) {
      $('[data-photo-no]').textContent = 'Photo ' + (idx + 1) + ' of ' + N;
      const t = idx * F.photoEveryS;
      $('[data-device-time]').textContent = 'Device time ' + Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0') + ' into the hour';
      drawTray(res);

      // list of detections
      const dets = res.dets;
      $('[data-dets]').innerHTML = dets.length
        ? dets.map(function (d) {
            const name = d.status === 'unidentified' ? 'Unidentified' : SPECIES[d.sp].name;
            const col = d.status === 'unidentified' ? 'var(--faint)' : SPECIES[d.sp].color;
            return '<li><span class="ai-dot" style="background:' + col + '"></span><span class="ai-det-name">' + esc(name) + ' <span class="ai-det-conf">' + d.conf.toFixed(2) + '</span></span><span class="ai-chip ai-chip-' + d.status + '">' + statusText(d.status) + '</span></li>';
          }).join('')
        : '<li class="ai-empty">Nothing on the tray.</li>';

      // latch panel
      const L = $('[data-latch]');
      L.classList.toggle('is-closed', S.latch);
      $('[data-latch-state]').textContent = S.latch ? 'Latch closed' : 'Latch open';
      let why;
      if (res.event === 'closed') why = 'Squirrel seen in ' + F.latchCloseAfter + ' photos in a row. The latch closes now.';
      else if (res.event === 'opened') why = F.latchOpenAfter + ' photos in a row without a squirrel. The latch opens now.';
      else if (S.latch) why = 'Waiting for ' + F.latchOpenAfter + ' photos in a row without a squirrel: ' + S.away + ' of ' + F.latchOpenAfter + ' so far.';
      else if (S.sq > 0) why = 'Squirrel seen in ' + S.sq + ' of ' + F.latchCloseAfter + ' photos needed to close the latch.';
      else why = 'No squirrel on the tray.';
      $('[data-latch-why]').textContent = why;

      // counts table
      $('[data-table]').innerHTML = BIRD_KEYS.map(function (k) {
        return '<tr class="' + (S.now[k] ? 'is-on' : '') + '"><th scope="row"><span class="ai-dot" style="background:' + SPECIES[k].color + '"></span>' + SPECIES[k].name + '</th><td class="ai-num">' + S.now[k] + '</td><td class="ai-num">' + S.max[k] + '</td></tr>';
      }).join('') +
        '<tr class="ai-sq-row"><th scope="row"><span class="ai-dot" style="background:' + SPECIES.squirrel.color + '"></span>Red squirrel</th><td class="ai-num" colspan="2">' + (res.sqSeen ? 'in frame, never counted' : 'never counted') + '</td></tr>';

      // pipeline text
      const found = dets.length;
      const unid = dets.filter(function (d) { return d.status === 'unidentified'; }).length;
      const conf = dets.filter(function (d) { return d.status === 'confirming'; }).length;
      const cnt = dets.filter(function (d) { return d.status === 'counted'; }).length;
      stepTexts[0].textContent = 'Camera takes photo ' + (idx + 1) + '.';
      stepTexts[1].textContent = found ? plural(found, 'object', 'objects') + ' found, each with a name and a confidence.' : 'Nothing found.';
      stepTexts[2].textContent = unid ? plural(unid, 'name', 'names') + ' under ' + thr + ' set aside as unidentified.' : 'All names at or above ' + thr + '.';
      stepTexts[3].textContent = cnt + ' seen twice in a row, ' + conf + ' still confirming.';
      stepTexts[4].textContent = 'Largest-at-once table updated.';
      stepTexts[5].textContent = S.latch ? 'Latch closed.' : (S.sq ? 'Squirrel seen, latch still open.' : 'Latch open.');
      runSteps();
    }

    function clearStepTimers() { stepTimers.forEach(clearTimeout); stepTimers = []; }
    function setStep(i) {
      stepNodes.forEach(function (n, j) { n.classList.toggle('is-active', j === i); n.classList.toggle('is-done', j < i); });
      $('[data-bar-use]').classList.toggle('is-on', i === 1);
    }
    function runSteps() {
      clearStepTimers();
      if (reduced) { stepNodes.forEach(function (n) { n.classList.remove('is-active'); n.classList.add('is-done'); }); return; }
      for (let i = 0; i < STEPS.length; i++) {
        stepTimers.push(setTimeout(function () { setStep(i); }, i * 190));
      }
    }

    function advance() {
      idx = (idx + 1) % N;
      if (idx === 0) resetState();
      render(process(idx));
    }
    function tick() { if (el.offsetParent === null) return; advance(); }

    function setPlaying(on) {
      if (timer) { clearInterval(timer); timer = null; }
      if (on) timer = setInterval(tick, TICK_MS);
      playBtn.textContent = on ? 'Pause' : 'Play';
      playBtn.setAttribute('aria-label', on ? 'Pause the simulation' : 'Play the simulation');
    }

    playBtn.addEventListener('click', function () { setPlaying(!timer); });
    $('[data-step]').addEventListener('click', function () { setPlaying(false); advance(); });
    $('[data-restart]').addEventListener('click', function () { idx = -1; resetState(); advance(); });

    advance();
    setPlaying(!reduced);
  };
})();
