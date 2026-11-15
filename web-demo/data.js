/* Feeder Census demo: shared data. Everything under FC.data.stations is SIMULATED for illustration.
   Loaded first; other modules read window.FC. */
(function () {
  const FC = (window.FC = window.FC || {});

  // deterministic random numbers so every viewer sees the same network
  function rng(seed) {
    let s = seed >>> 0;
    return function () {
      s = (s + 0x6d2b79f5) >>> 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // The 12 bird species the shipped model can name. group = our own habitat grouping (not checked with Luomus).
  const species = [
    { id: 'great_tit', name: 'Great tit', fi: 'talitiainen', group: 'generalist', color: '#C99700', base: 7.0 },
    { id: 'blue_tit', name: 'Blue tit', fi: 'sinitiainen', group: 'generalist', color: '#3E7FC1', base: 4.0 },
    { id: 'bullfinch', name: 'Bullfinch', fi: 'punatulkku', group: 'forest', color: '#C8553F', base: 2.2 },
    { id: 'willow_tit', name: 'Willow tit', fi: 'hömötiainen', group: 'forest', color: '#8C7A62', base: 1.6 },
    { id: 'crested_tit', name: 'Crested tit', fi: 'töyhtötiainen', group: 'forest', color: '#6E5FB3', base: 1.0 },
    { id: 'coal_tit', name: 'Coal tit', fi: 'kuusitiainen', group: 'forest', color: '#3F8F78', base: 1.1 },
    { id: 'woodpecker', name: 'Great spotted woodpecker', fi: 'käpytikka', group: 'forest', color: '#B5345A', base: 0.9 },
    { id: 'jay', name: 'Jay', fi: 'närhi', group: 'forest', color: '#A0528E', base: 0.8 },
    { id: 'nuthatch', name: 'Nuthatch', fi: 'pähkinänakkeli', group: 'forest', color: '#4B6FA6', base: 0.3 },
    { id: 'tree_sparrow', name: 'Tree sparrow', fi: 'pikkuvarpunen', group: 'town', color: '#B5722E', base: 5.0 },
    { id: 'house_sparrow', name: 'House sparrow', fi: 'varpunen', group: 'town', color: '#7C8C2E', base: 2.5 },
    { id: 'magpie', name: 'Magpie', fi: 'harakka', group: 'town', color: '#4A5A57', base: 1.4 },
  ];

  // Luomus reports October to April in half-month periods: 14 periods.
  const months = [['Oct', 31], ['Nov', 30], ['Dec', 31], ['Jan', 31], ['Feb', 28], ['Mar', 31], ['Apr', 30]];
  const periods = [];
  months.forEach(([m, days], i) => {
    periods.push({ id: i * 2, label: '1–15 ' + m, short: m + ' I', month: m });
    periods.push({ id: i * 2 + 1, label: '16–' + days + ' ' + m, short: m + ' II', month: m });
  });

  // name, lat, lon, habitat
  const places = [
    ['Hanko', 59.82, 22.97, 'town'], ['Helsinki', 60.17, 24.94, 'town'], ['Espoo', 60.21, 24.66, 'town'],
    ['Porvoo', 60.39, 25.66, 'farmland'], ['Salo', 60.38, 23.13, 'farmland'], ['Turku', 60.45, 22.27, 'town'],
    ['Kotka', 60.47, 26.95, 'town'], ['Kouvola', 60.87, 26.70, 'farmland'], ['Lahti', 60.98, 25.66, 'town'],
    ['Hämeenlinna', 60.99, 24.46, 'farmland'], ['Lappeenranta', 61.06, 28.19, 'town'], ['Rauma', 61.13, 21.51, 'town'],
    ['Pori', 61.48, 21.80, 'farmland'], ['Tampere', 61.50, 23.76, 'town'], ['Mikkeli', 61.69, 27.27, 'forest'],
    ['Savonlinna', 61.87, 28.88, 'forest'], ['Jyväskylä', 62.24, 25.75, 'forest'], ['Varkaus', 62.31, 27.87, 'forest'],
    ['Joensuu', 62.60, 29.76, 'forest'], ['Seinäjoki', 62.79, 22.84, 'farmland'], ['Kuopio', 62.89, 27.68, 'town'],
    ['Vaasa', 63.10, 21.62, 'farmland'], ['Lieksa', 63.32, 30.02, 'forest'], ['Nurmes', 63.54, 29.14, 'forest'],
    ['Iisalmi', 63.56, 27.19, 'farmland'], ['Kokkola', 63.84, 23.13, 'farmland'], ['Ylivieska', 64.07, 24.54, 'farmland'],
    ['Kajaani', 64.22, 27.73, 'forest'], ['Oulu', 65.01, 25.47, 'town'], ['Haukipudas', 65.18, 25.35, 'forest'],
    ['Kemi', 65.74, 24.56, 'town'], ['Tornio', 65.85, 24.15, 'farmland'], ['Kuusamo', 65.96, 29.18, 'forest'],
    ['Rovaniemi', 66.50, 25.72, 'town'], ['Kemijärvi', 66.71, 27.43, 'forest'], ['Sodankylä', 67.42, 26.59, 'forest'],
    ['Kittilä', 67.65, 24.91, 'forest'], ['Muonio', 67.96, 23.68, 'forest'], ['Inari', 68.91, 27.03, 'forest'],
    ['Utsjoki', 69.91, 27.03, 'forest'],
  ];

  // habitat multipliers per species group
  const habMult = {
    town: { generalist: 1.15, forest: 0.35, town: 1.6 },
    farmland: { generalist: 1.0, forest: 0.6, town: 1.2 },
    forest: { generalist: 0.85, forest: 1.5, town: 0.25 },
  };
  // how fast a species thins out going north (0 = everywhere, 1 = southern only)
  const southern = { blue_tit: 0.75, nuthatch: 0.95, tree_sparrow: 0.8, house_sparrow: 0.45, jay: 0.5, coal_tit: 0.6,
    crested_tit: 0.45, magpie: 0.2, great_tit: 0.15, bullfinch: 0.15, woodpecker: 0.25, willow_tit: -0.35 };

  function daylightHours(lat, periodIdx) {
    // rough daylight for the middle of each half-month, Oct..Apr; enough for an illustration
    const dayOfYear = [281, 297, 312, 327, 342, 357, 8, 24, 39, 53, 67, 83, 98, 113][periodIdx];
    const decl = -23.44 * Math.cos((2 * Math.PI * (dayOfYear + 10)) / 365);
    const x = -Math.tan((lat * Math.PI) / 180) * Math.tan((decl * Math.PI) / 180);
    if (x >= 1) return 0.5; // polar night: twilight only
    if (x <= -1) return 24;
    return (24 * Math.acos(x)) / Math.PI;
  }

  const stations = places.map(([name, lat, lon, habitat], i) => {
    const r = rng(1000 + i * 37);
    const north = Math.min(1, Math.max(0, (lat - 60) / 9.5)); // 0 south coast .. 1 far north
    const siteFactor = 0.7 + r() * 0.7;
    const counts = {};
    species.forEach((sp) => {
      const s = southern[sp.id];
      const latF = s >= 0 ? Math.max(0, 1 - s * north * 1.6) : 1 + -s * north * 2;
      const present = r() < Math.min(1, 0.25 + latF * habMult[habitat][sp.group]);
      counts[sp.id] = periods.map((p, t) => {
        if (!present) return 0;
        // feeders get busier towards midwinter, then thin out in spring
        const season = 0.55 + 0.6 * Math.exp(-Math.pow((t - 6.5) / 4.2, 2));
        const mean = sp.base * habMult[habitat][sp.group] * latF * siteFactor * season;
        const v = mean * (0.65 + r() * 0.7);
        return Math.max(0, Math.round(v));
      });
    });
    const hours = periods.map((p, t) => {
      const days = p.label.startsWith('1–15') ? 15 : parseInt(p.label.slice(3), 10) - 15;
      return Math.round(daylightHours(lat, t) * days);
    });
    return { id: 's' + i, name, lat, lon, habitat, counts, hours };
  });

  // Stylised outline of Finland as [lon, lat], clockwise from Hanko. Not survey-accurate.
  const outline = [
    [22.9, 59.8], [24.0, 59.95], [25.0, 60.15], [26.0, 60.3], [26.9, 60.45], [27.8, 60.55], [28.6, 61.0],
    [29.3, 61.3], [30.0, 61.8], [30.9, 62.3], [31.55, 62.9], [31.2, 63.3], [30.0, 63.75], [30.5, 64.25],
    [29.7, 64.8], [29.65, 65.6], [30.1, 65.7], [29.7, 66.3], [29.1, 66.9], [29.9, 67.6], [28.6, 68.2],
    [28.45, 68.9], [28.95, 69.05], [29.3, 69.5], [27.9, 70.08], [26.5, 69.95], [25.95, 69.65], [25.75, 69.3],
    [24.9, 68.6], [23.2, 68.65], [22.4, 68.75], [21.6, 69.25], [20.6, 69.06], [21.9, 68.5], [23.3, 68.15],
    [23.65, 67.9], [23.55, 67.2], [23.95, 66.8], [23.65, 66.3], [24.15, 65.8], [24.6, 65.7], [25.3, 65.5],
    [25.45, 65.0], [24.6, 64.75], [24.0, 64.3], [23.1, 63.85], [22.3, 63.3], [21.5, 63.15], [21.1, 62.6],
    [21.3, 62.0], [21.5, 61.5], [21.3, 61.1], [21.25, 60.8], [21.7, 60.5], [22.3, 60.25], [22.9, 59.8],
  ];

  // Simple map projection: returns x, y in 0..1 of a box whose aspect ratio is FC.mapAspect (width / height).
  const LON0 = 19.8, LON1 = 32.0, LAT0 = 59.5, LAT1 = 70.3, K = Math.cos((65 * Math.PI) / 180);
  FC.mapAspect = ((LON1 - LON0) * K) / (LAT1 - LAT0);
  FC.project = function (lon, lat) {
    return { x: (lon - LON0) / (LON1 - LON0), y: (LAT1 - lat) / (LAT1 - LAT0) };
  };

  FC.data = { species, periods, stations, outline, groups: ['forest', 'town', 'generalist'] };

  // Facts measured by the team (from the project README, 14 November 2026). These are real, not simulated.
  FC.facts = {
    msPerPhoto: 507, budgetMs: 1500, photoEveryS: 5, modelMB: 10, classes: 13, countThreshold: 0.5,
    testFrames: 899, testDay: '12 November 2026', countedRight: 0.84, namedRight: 0.9, birdsFound: 0.84,
    trainingDays: 25, trainingFrames: 62185, labelledBoxes: 88466, latchCloseAfter: 2, latchOpenAfter: 5, failsafeS: 30,
  };

  // helpers other modules may use
  FC.util = {
    stationTotal(st, period) { return species.reduce((a, sp) => a + st.counts[sp.id][period], 0); },
    stationSpeciesCount(st, period) { return species.filter((sp) => st.counts[sp.id][period] > 0).length; },
    networkMean(spId, period) { return stations.reduce((a, st) => a + st.counts[spId][period], 0) / stations.length; },
    speciesById(id) { return species.find((s) => s.id === id); },
  };
})();
