# BirdAI web demo

A single static page that presents BirdAI: what it is, why it matters, how it works, the model running on the Arduino UNO Q, and what a network of feeders could be used for.

## Run it

Serve this folder with any static file server and open the page:

```
python -m http.server 8000 --directory web-demo
```

Then open http://localhost:8000. Opening `index.html` straight from disk also works, but some browsers block autoplaying video from `file://`.

## What is real and what is not

- Real: the photo of the prototype, the squirrel detection footage (`clips/feeder-ai.mp4`), and the speed and accuracy figures, which come from the project README.
- 3D animation: `hero.mp4`, `xray.mp4`, `birds.mp4`, `squirrel.mp4`, `forest.mp4` and the background image.
- Illustration: the Espoo network map (`clips/network.png`, map data © OpenStreetMap contributors). No such network exists yet.
- The bird statistics in the Why section are cited on the page (Eurostat 2026, Fraixedas et al. 2020, Luomus).

The feeder footage comes from a third-party feeder stream. Check with its owner before publishing this page outside the team.

## Files

- `index.html`: the whole page, with its styles and a small script for scroll effects.
- `clips/`: the videos and images the page uses.

Fonts load from Google Fonts. Nothing else is fetched from the network.
