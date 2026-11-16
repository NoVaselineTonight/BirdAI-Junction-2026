/* Feeder Census demo: the device simulator. It applies the same rules as the real program
   (photo every 5 s, cut-off, two photos in a row, largest at once, squirrel latch, 30 s failsafe)
   to simulated visitors. The picture is drawn, not filmed. Defines FC.createSim and FC.drawSim. */
(function () {
  const FC = (window.FC = window.FC || {});
  const W = 640, H = 400;
  const SQ = { id: 'red_squirrel', name: 'Red squirrel', color: '#E8763A' };
  const rnd = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const noise = () => Math.random() + Math.random() + Math.random() - 1.5; // roughly bell-shaped, sd 0.5

  FC.createSim = function (opt) {
    opt = opt || {};
    const species = FC.data.species;
    const F = FC.facts;
    const weightSum = species.reduce((a, s) => a + s.base, 0);
    let uid = 0;
    const listeners = [];
    const S = {
      W, H, t: 0, clock0: 10 * 3600, birds: [], squirrel: null,
      photoNo: 0, nextPhoto: 1, lastPhotoT: -5, analysing: null, dets: [], detsAge: 0,
      prev: {}, now: {}, max: {}, sum: {}, hist: [],
      sqStreak: 0, clearStreak: 0, want: 'open', angle: 180, target: 180, lastClose: -1e9, closedAt: null, failsafe: false,
      running: true, auto: opt.auto !== false, threshold: F.countThreshold, interval: F.photoEveryS, detector: 'student640',
      log: [],
    };
    species.forEach((s) => { S.prev[s.id] = 0; S.now[s.id] = 0; S.max[s.id] = 0; S.sum[s.id] = 0; });

    function clock(t) {
      const c = Math.floor(S.clock0 + (t === undefined ? S.t : t));
      const p = (n) => String(n).padStart(2, '0');
      return p(Math.floor(c / 3600) % 24) + ':' + p(Math.floor(c / 60) % 60) + ':' + p(c % 60);
    }
    function log(kind, text) {
      S.log.push({ time: clock(), kind, text });
      if (S.log.length > 80) S.log.shift();
      emit('log');
    }
    function emit(ev) { listeners.forEach((f) => f(ev, S)); }

    function randomSpecies() {
      let r = Math.random() * weightSum;
      for (const s of species) { r -= s.base; if (r <= 0) return s.id; }
      return species[0].id;
    }
    function edgePoint() {
      const side = Math.floor(Math.random() * 3); // left, right, bottom: the hatch is at the top
      if (side === 0) return [-50, rnd(120, H - 40)];
      if (side === 1) return [W + 50, rnd(120, H - 40)];
      return [rnd(60, W - 60), H + 50];
    }
    function addBird(sp, x, y) {
      if (S.birds.length >= 9) return null;
      const from = edgePoint();
      const b = {
        id: ++uid, sp: sp || randomSpecies(), x: from[0], y: from[1],
        tx: clamp(x === undefined ? rnd(70, W - 70) : x, 60, W - 60), ty: clamp(y === undefined ? rnd(120, H - 55) : y, 110, H - 50),
        q: Math.random() < 0.8 ? rnd(0.8, 0.95) : rnd(0.36, 0.6), // some birds are half hidden and harder to name
        face: Math.random() < 0.5 ? 1 : -1, hop: S.t + rnd(3, 9), leave: S.t + rnd(25, 110), out: false,
      };
      S.birds.push(b);
      return b;
    }
    function sendSquirrel() {
      if (S.squirrel) return;
      S.squirrel = { id: ++uid, sq: true, x: W / 2 + rnd(-60, 60), y: -70, tx: W / 2 + rnd(-40, 40), ty: 150, q: rnd(0.88, 0.96), leave: S.t + rnd(45, 70), out: false };
      log('sys', 'A red squirrel climbs onto the tray');
    }
    function clearTray() {
      S.birds.forEach((b) => leave(b));
      if (S.squirrel) leave(S.squirrel);
    }
    function leave(a) {
      if (a.out) return;
      a.out = true;
      const e = a.sq ? [a.x, -90] : edgePoint();
      a.tx = e[0]; a.ty = e[1];
    }

    function process(snap) {
      const D = FC.detectors[S.detector];
      const dets = [];
      snap.forEach((a) => {
        if (Math.random() > (a.sq ? D.sq : D.found)) return; // the model missed it in this photo
        let sp = a.sq ? SQ.id : a.sp;
        if (!a.sq && Math.random() > D.right) { // named wrong
          let other = randomSpecies();
          if (other === sp) other = species[(species.findIndex((s) => s.id === sp) + 1) % species.length].id;
          sp = other;
        }
        dets.push({ ref: a.ref, x: a.x, y: a.y, sq: !!a.sq, sp, conf: clamp(a.q + noise() * 0.07, 0.25, 0.99) });
      });
      const n = {};
      species.forEach((s) => { n[s.id] = 0; });
      let sqSeen = false;
      dets.sort((a, b) => b.conf - a.conf).forEach((d) => {
        if (d.conf < S.threshold) { d.status = 'unid'; return; }
        if (d.sq) { d.status = 'pest'; sqSeen = true; return; }
        n[d.sp]++;
        d.status = n[d.sp] <= S.prev[d.sp] ? 'counted' : 'confirming';
      });
      let total = 0;
      species.forEach((s) => {
        const c = Math.min(n[s.id], S.prev[s.id]); // seen in two photos in a row
        S.now[s.id] = c; total += c;
        if (c > S.max[s.id]) S.max[s.id] = c;
        S.sum[s.id] += n[s.id];
        S.prev[s.id] = n[s.id];
      });
      S.dets = dets; S.detsAge = 0;
      S.hist.push(total);
      if (S.hist.length > 60) S.hist.shift();

      const names = dets.map((d) => (d.status === 'unid' ? 'unidentified' : d.sp) + ' ' + d.conf.toFixed(2));
      log('photo', 'photo ' + String(S.photoNo).padStart(4, '0') + '  ' + Math.round(D.ms) + ' ms  ' + (names.length ? names.join(', ') : 'nothing found'));

      if (sqSeen) { S.sqStreak++; S.clearStreak = 0; } else { S.sqStreak = 0; S.clearStreak++; }
      if (S.want === 'open' && S.sqStreak >= F.latchCloseAfter) {
        S.want = 'closed'; S.closedAt = S.t;
        log('latch', 'squirrel in ' + F.latchCloseAfter + ' photos in a row: set_latch(closed)');
      } else if (S.want === 'closed' && S.clearStreak >= F.latchOpenAfter) {
        S.want = 'open'; S.target = 180; S.closedAt = null; S.failsafe = false;
        log('latch', F.latchOpenAfter + ' photos in a row without it: set_latch(open)');
      }
      if (S.want === 'closed') { S.target = 0; S.lastClose = S.t; S.failsafe = false; } // close is repeated at every detection
      emit('photo');
    }

    function advance(dt, real) {
      S.t += dt;
      S.detsAge += dt;
      // visitors
      if (S.auto && S.birds.length < 6 && Math.random() < dt * (S.birds.length < 2 ? 0.12 : 0.045)) addBird();
      if (S.auto && !S.squirrel && Math.random() < dt / 260) sendSquirrel();
      const k = Math.min(1, real * 6);
      const move = (a) => {
        a.x += (a.tx - a.x) * k; a.y += (a.ty - a.y) * k;
        if (!a.out && S.t > a.leave) leave(a);
      };
      S.birds.forEach((b) => {
        if (!b.out && S.t > b.hop) {
          b.hop = S.t + rnd(3, 10);
          b.tx = clamp(b.tx + rnd(-70, 70), 60, W - 60); b.ty = clamp(b.ty + rnd(-45, 45), 110, H - 50);
          b.face = b.tx > b.x ? 1 : -1;
        }
        move(b);
      });
      S.birds = S.birds.filter((b) => !(b.out && (b.x < -40 || b.x > W + 40 || b.y > H + 40)));
      if (S.squirrel) {
        const q = S.squirrel;
        if (!q.out && S.angle < 20 && S.closedAt !== null && S.t - S.closedAt > 14) leave(q); // nothing to eat behind a shut hatch
        move(q);
        if (q.out && q.y < -60) { S.squirrel = null; log('sys', 'The squirrel leaves'); }
      }
      // Linux side: photo, then inference
      if (S.running) {
        if (!S.analysing && S.t >= S.nextPhoto) {
          S.photoNo++; S.lastPhotoT = S.t; S.nextPhoto = S.t + S.interval;
          const snap = S.birds.concat(S.squirrel ? [S.squirrel] : []).filter((a) => a.x > 20 && a.x < W - 20 && a.y > 20 && a.y < H - 20)
            .map((a) => ({ ref: a, sq: a.sq, sp: a.sp, x: a.x, y: a.y, q: a.q }));
          S.analysing = { until: S.t + FC.detectors[S.detector].ms / 1000, snap };
          emit('shutter');
        }
        if (S.analysing && S.t >= S.analysing.until) { const a = S.analysing; S.analysing = null; process(a.snap); }
      }
      // microcontroller side: servo steps 10 degrees every 0.1 s, and reopens by itself
      if (S.target === 0 && S.t - S.lastClose > F.failsafeS) {
        S.target = 180; S.failsafe = true;
        log('mcu', 'microcontroller: no close command for ' + F.failsafeS + ' s, opening by itself');
        emit('photo');
      }
      const stepDeg = 100 * dt;
      if (S.angle < S.target) S.angle = Math.min(S.target, S.angle + stepDeg);
      else if (S.angle > S.target) S.angle = Math.max(S.target, S.angle - stepDeg);
    }

    const api = {
      state: S, W, H, advance, addBird, sendSquirrel, clearTray, clock,
      on(f) { listeners.push(f); },
      flock() { const sp = randomSpecies(); for (let i = 0; i < 5; i++) addBird(sp); log('sys', 'A flock of five lands'); },
      setRunning(on) {
        if (S.running === on) return;
        S.running = on; S.analysing = null;
        if (on) { S.nextPhoto = S.t + 1; S.sqStreak = 0; S.clearStreak = 0; S.want = 'open'; species.forEach((s) => { S.prev[s.id] = 0; }); log('sys', 'feeder_census started: counts continue from the saved table'); }
        else { S.dets = []; species.forEach((s) => { S.now[s.id] = 0; }); log('sys', 'feeder_census stopped: no more commands reach the microcontroller'); }
        emit('photo');
      },
      setDetector(id) { S.detector = id; log('sys', 'detector: ' + FC.detectors[id].name); emit('photo'); },
      setThreshold(v) { S.threshold = v; },
      resetCounts() { species.forEach((s) => { S.max[s.id] = 0; S.sum[s.id] = 0; }); S.hist = []; emit('photo'); },
    };
    log('sys', 'feeder_census --camera 0 --photo-every-s 5 --latch router');
    for (let i = 0; i < (opt.seedBirds === undefined ? 3 : opt.seedBirds); i++) { const b = addBird(); b.x = b.tx; b.y = b.ty; }
    return api;
  };

  /* ---------- drawing ---------- */
  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    const c = (v) => Math.round(clamp(v * f, 0, 255));
    return 'rgb(' + c(n >> 16) + ',' + c((n >> 8) & 255) + ',' + c(n & 255) + ')';
  }
  function drawBird(ctx, b, color) {
    ctx.save(); ctx.translate(b.x, b.y); ctx.scale(b.face || 1, 1);
    ctx.fillStyle = 'rgba(0,0,0,.22)'; ctx.beginPath(); ctx.ellipse(2, 16, 26, 7, 0, 0, 7); ctx.fill();
    ctx.fillStyle = shade(color, 0.7); ctx.beginPath(); ctx.roundRect(-44, -6, 26, 9, 4); ctx.fill();
    ctx.fillStyle = color; ctx.beginPath(); ctx.ellipse(0, 0, 26, 17, 0, 0, 7); ctx.fill();
    ctx.fillStyle = shade(color, 0.62); ctx.beginPath(); ctx.ellipse(-5, -2, 15, 9, -0.25, 0, 7); ctx.fill();
    ctx.fillStyle = color; ctx.beginPath(); ctx.arc(22, -8, 11, 0, 7); ctx.fill();
    ctx.fillStyle = shade(color, 0.45); ctx.beginPath(); ctx.arc(22, -8, 11, Math.PI * 1.05, Math.PI * 1.95); ctx.fill();
    ctx.fillStyle = '#10140F'; ctx.beginPath(); ctx.arc(26, -9, 2.2, 0, 7); ctx.fill();
    ctx.fillStyle = '#E9C98B'; ctx.beginPath(); ctx.moveTo(32, -9); ctx.lineTo(42, -6); ctx.lineTo(32, -3); ctx.fill();
    ctx.restore();
  }
  function drawSquirrel(ctx, q) {
    ctx.save(); ctx.translate(q.x, q.y);
    ctx.fillStyle = 'rgba(0,0,0,.22)'; ctx.beginPath(); ctx.ellipse(0, 22, 44, 9, 0, 0, 7); ctx.fill();
    ctx.fillStyle = shade(SQ.color, 0.8); ctx.beginPath(); ctx.ellipse(-48, -16, 40, 17, -0.5, 0, 7); ctx.fill();
    ctx.fillStyle = SQ.color; ctx.beginPath(); ctx.ellipse(0, 0, 34, 21, 0, 0, 7); ctx.fill();
    ctx.beginPath(); ctx.arc(34, -6, 14, 0, 7); ctx.fill();
    ctx.beginPath(); ctx.moveTo(29, -17); ctx.lineTo(33, -31); ctx.lineTo(40, -17); ctx.fill();
    ctx.fillStyle = '#F3DEC4'; ctx.beginPath(); ctx.ellipse(6, 7, 17, 8, 0, 0, 7); ctx.fill();
    ctx.fillStyle = '#10140F'; ctx.beginPath(); ctx.arc(40, -9, 2.6, 0, 7); ctx.fill();
    ctx.restore();
  }
  const BOX = { counted: '#9CC7D4', confirming: '#F2C230', unid: '#93A19E', pest: '#FF5A4F' };
  const WORD = { counted: 'counted', confirming: 'confirming', unid: 'not counted', pest: 'never counted' };
  const SEEDS = [[70, 150], [120, 350], [250, 130], [380, 340], [590, 140], [600, 250], [50, 250], [470, 120], [210, 250], [340, 260], [95, 320], [545, 360], [300, 185], [430, 215], [160, 205]];

  FC.drawSim = function (ctx, sim, o) {
    o = o || {};
    const S = sim.state, mono = '"Alegreya Sans", "Segoe UI", sans-serif';
    ctx.clearRect(0, 0, W, H);
    // tray seen from above
    ctx.fillStyle = '#0A1113'; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = '#B4925F'; ctx.beginPath(); ctx.roundRect(14, 60, W - 28, H - 74, 14); ctx.fill();
    ctx.strokeStyle = 'rgba(70,48,22,.35)'; ctx.lineWidth = 1.5;
    for (let y = 60 + 67; y < H - 20; y += 67) { ctx.beginPath(); ctx.moveTo(14, y); ctx.lineTo(W - 14, y); ctx.stroke(); }
    ctx.fillStyle = 'rgba(38,28,16,.8)';
    SEEDS.forEach((p) => { ctx.beginPath(); ctx.ellipse(p[0], p[1], 3.4, 2.2, p[0], 0, 7); ctx.fill(); });
    // seed slot and hatch (open = lifted, closed = hanging over the slot)
    const shut = 1 - S.angle / 180;
    ctx.fillStyle = '#1B140B'; ctx.beginPath(); ctx.roundRect(W / 2 - 150, 68, 300, 34, 6); ctx.fill();
    ctx.fillStyle = '#E3C47A';
    for (let i = 0; i < 38; i++) { ctx.beginPath(); ctx.arc(W / 2 - 138 + ((i * 53) % 276), 76 + ((i * 29) % 20), 2.4, 0, 7); ctx.fill(); }
    ctx.fillStyle = shut > 0.5 ? '#7A3B2E' : '#6E5433';
    ctx.beginPath(); ctx.roundRect(W / 2 - 158, 62, 316, 8 + 36 * shut, 5); ctx.fill();
    ctx.fillStyle = '#070C0D'; ctx.fillRect(0, 0, W, 60 - 0);
    // animals
    S.birds.forEach((b) => drawBird(ctx, b, FC.util.speciesById(b.sp).color));
    if (S.squirrel) drawSquirrel(ctx, S.squirrel);
    // boxes from the last analysed photo
    ctx.font = '700 15px ' + mono; ctx.textBaseline = 'middle';
    S.dets.forEach((d) => {
      if (d.ref && !d.ref.out) { d.x = d.ref.x; d.y = d.ref.y; } // the box stays on its animal until the next photo
      const w = d.sq ? 168 : 100, h = d.sq ? 104 : 70, x = d.x - w / 2 - (d.sq ? 8 : 0), y = d.y - h / 2 - 3, c = BOX[d.status];
      ctx.strokeStyle = c; ctx.lineWidth = 2.5; ctx.setLineDash(d.status === 'unid' ? [7, 5] : []);
      ctx.strokeRect(x, y, w, h); ctx.setLineDash([]);
      const name = d.status === 'unid' ? 'unidentified' : d.sq ? SQ.name : FC.util.speciesById(d.sp).name;
      const text = name + ' ' + d.conf.toFixed(2) + (o.compact ? '' : ' · ' + WORD[d.status]);
      const tw = ctx.measureText(text).width + 12, lx = clamp(x - 1, 2, W - tw - 2), ly = Math.max(62, y - 20);
      ctx.fillStyle = c; ctx.fillRect(lx, ly, tw, 20);
      ctx.fillStyle = '#0C1416'; ctx.fillText(text, lx + 6, ly + 10.5);
    });
    // inference sweep
    if (S.analysing) {
      const D = FC.detectors[S.detector], p = clamp(1 - (S.analysing.until - S.t) / (D.ms / 1000), 0, 1);
      ctx.fillStyle = 'rgba(156,199,212,.10)'; ctx.fillRect(0, 60, W * p, H - 60);
      ctx.fillStyle = '#9CC7D4'; ctx.fillRect(W * p - 1, 60, 2, H - 60);
    }
    // camera frame and readouts
    ctx.strokeStyle = S.angle < 90 ? '#FF5A4F' : 'rgba(242,245,243,.6)'; ctx.lineWidth = 2;
    [[8, 66, 1, 1], [W - 8, 66, -1, 1], [8, H - 8, 1, -1], [W - 8, H - 8, -1, -1]].forEach((c) => {
      ctx.beginPath(); ctx.moveTo(c[0], c[1] + 22 * c[3]); ctx.lineTo(c[0], c[1]); ctx.lineTo(c[0] + 22 * c[2], c[1]); ctx.stroke();
    });
    ctx.font = '500 15px ' + mono; ctx.fillStyle = '#F2F5F3';
    ctx.fillText('SIMULATION', 14, 20); ctx.fillStyle = '#93A19E'; ctx.fillText('not live video', 14, 40);
    ctx.textAlign = 'right'; ctx.fillStyle = '#F2F5F3'; ctx.fillText(sim.clock(), W - 14, 20);
    ctx.fillStyle = S.running ? (S.analysing ? '#9CC7D4' : '#93A19E') : '#FF5A4F';
    ctx.fillText(S.running ? (S.analysing ? 'analysing photo ' + String(S.photoNo).padStart(4, '0') : 'photo ' + String(S.photoNo).padStart(4, '0')) : 'program stopped', W - 14, 40);
    ctx.textAlign = 'center';
    ctx.fillStyle = S.angle < 90 ? '#FF5A4F' : '#A8C9A0';
    ctx.fillText(S.angle <= 0 ? 'LATCH CLOSED' : S.angle >= 180 ? 'LATCH OPEN' : 'LATCH MOVING ' + Math.round(S.angle) + '°', W / 2, 30);
    ctx.textAlign = 'left';
  };

  /* Wire a canvas to a simulator. Returns { sim, canvas, speed }. */
  FC.runSim = function (canvas, opt) {
    const sim = FC.createSim(opt);
    const ctx = canvas.getContext('2d');
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = W * ratio; canvas.height = H * ratio;
    ctx.scale(ratio, ratio);
    const h = { sim, canvas, speed: opt.speed || 4, paused: false, onFrame: null };
    let last = 0;
    function frame(ts) {
      requestAnimationFrame(frame);
      const real = Math.min(0.1, (ts - last) / 1000 || 0); last = ts;
      if (canvas.offsetParent === null) return; // view hidden
      if (!h.paused) {
        let dt = real * h.speed;
        while (dt > 0) { const s = Math.min(0.05, dt); sim.advance(s, s / h.speed); dt -= s; }
      }
      FC.drawSim(ctx, sim, opt);
      if (h.onFrame) h.onFrame();
    }
    requestAnimationFrame(frame);
    return h;
  };
})();
