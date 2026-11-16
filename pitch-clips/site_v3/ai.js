/* BirdAI demo: "The AI" view. Detection footage, one cut-off demo on a real frame, and the deck's edge points. */
(function () {
  const FC = (window.FC = window.FC || {});
  // Boxes the model drew on this frame (1280 x 720): name, confidence, x0, y0, x1, y1.
  const BOXES = [
    ['Great tit', 0.94, 692, 172, 872, 347], ['Great tit', 0.91, 316, 317, 498, 397], ['Great tit', 0.53, 762, 337, 942, 517],
    ['Great tit', 0.95, 677, 410, 860, 507], ['Great tit', 0.89, 482, 455, 664, 627], ['Blue tit', 0.95, 613, 580, 780, 690],
  ];

  FC.mountAI = function (el) {
    el.innerHTML =
      '<div class="slide">' +
        '<p class="label">The AI</p><h1>Why it runs on edge</h1>' +
        '<figure class="video"><video class="media" src="clips/feeder-ai.mp4" controls autoplay muted loop playsinline aria-label="Feeder camera footage with a box labelled Red squirrel following a squirrel up a pole"></video></figure>' +
      '</div>' +

      '<div class="slide">' +
        '<p class="label">Try it</p><h2>How sure does it need to be?</h2>' +
        '<div class="cut">' +
          '<div class="cut-frame"><img class="media" src="clips/birds-still.jpg" alt="Feeder camera frame with six birds in labelled boxes"><div data-covers></div></div>' +
          '<div class="cut-side">' +
            '<label class="label" for="cut-range">Cut-off</label>' +
            '<output class="cut-val" for="cut-range" data-val></output>' +
            '<input type="range" id="cut-range" min="0.25" max="0.99" step="0.01" value="0.5">' +
            '<p class="cut-count"><b data-n></b><span data-what></span></p>' +
            '<p class="credit">We ship 0.50.</p>' +
          '</div>' +
        '</div>' +
      '</div>' +

      '<div class="slide">' +
        '<p class="label">Why edge AI?</p>' +
        '<div class="cols four">' +
          '<div class="col"><h3>Offline</h3><p>It counts without a network connection.</p></div>' +
          '<div class="col"><h3>Efficient</h3><p>It sends a table of counts, never photos.</p></div>' +
          '<div class="col"><h3>Cheap</h3><p>One board runs the camera, the model and the hatch.</p></div>' +
          '<div class="col"><h3>Private</h3><p>The pictures stay on the device.</p></div>' +
        '</div>' +
      '</div>' +

      '<div class="slide">' +
        '<p class="label">The numbers</p>' +
        '<div class="cols">' +
          '<div class="num"><b>0.5 s</b><span>to analyse a photo on the Arduino</span></div>' +
          '<div class="num"><b>94%</b><span>of named birds named right</span></div>' +
          '<div class="num"><b>89%</b><span>of birds found</span></div>' +
        '</div>' +
        '<p class="credit">Our own test on footage kept out of training: 12 November 2026, 899 frames.</p>' +
      '</div>';

    const covers = el.querySelector('[data-covers]'), range = el.querySelector('#cut-range');
    covers.innerHTML = BOXES.map((b) => '<span style="left:' + (b[2] / 12.8) + '%;top:' + (b[3] / 7.2) + '%;width:' + ((b[4] - b[2]) / 12.8) + '%;height:' + ((b[5] - b[3]) / 7.2) + '%"></span>').join('');
    const spans = covers.querySelectorAll('span');
    function draw() {
      const v = Number(range.value);
      let great = 0, blue = 0;
      BOXES.forEach((b, i) => {
        const on = b[1] >= v;
        spans[i].classList.toggle('is-off', !on);
        if (on) { if (b[0] === 'Great tit') great++; else blue++; }
      });
      el.querySelector('[data-val]').textContent = v.toFixed(2);
      el.querySelector('[data-n]').textContent = great + blue;
      el.querySelector('[data-what]').textContent = (great + blue === 1 ? ' bird counted' : ' birds counted') + (great + blue ? ': ' + [great ? great + ' great tit' + (great > 1 ? 's' : '') : '', blue ? blue + ' blue tit' : ''].filter(Boolean).join(', ') : '');
    }
    range.addEventListener('input', draw);
    draw();
  };
})();
