# Feeder Census web demo

A static, illustrative demo of Feeder Census. No build step and no server code: open `index.html` through any static file server.

```
cd web-demo
python -m http.server 8000
```

Then open http://localhost:8000.

## What it shows

- **Explore the AI**: a simulation of the loop the Arduino UNO Q runs every 5 seconds (photo, detect, filter, confirm, record, latch), the team's measured numbers, and two 3D animations of the build.
- **Explore the implications**: a map of 40 feeder stations across Finland with the half-month counts each would report, a station's monitoring form as a heat table, its habitat mix, and a network-wide winter curve.

## What is real and what is not

- The measured numbers (`FC.facts` in `data.js`) come from the project's own tests on 14 November 2026.
- The tray in "Explore the AI" is a scripted simulation, not video or detections from the device.
- The 40 stations and all their counts are **simulated** (`data.js` generates them from a fixed seed). One prototype feeder exists today.
- The outline of Finland is hand-drawn and stylised.
- The clips in `clips/` are 3D animations of the build, not footage from the device.

## Files

| File | What it is |
|---|---|
| `index.html` | Page shell, theme and routing between the three views |
| `data.js` | Species, periods, simulated stations, map projection, measured facts |
| `ai.js`, `ai.css` | The loop simulation and the edge-compute view |
| `map.js`, `map.css` | The Finland map, species picker and period slider |
| `charts.js`, `charts.css` | The station heat table, habitat mix and network charts |
| `clips/` | Three short 3D animations (MP4) |
