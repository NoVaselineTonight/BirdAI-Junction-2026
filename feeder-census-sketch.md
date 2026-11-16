---
title: "Feeder Census: idea sketch"
subtitle: "An Arduino camera that counts winter feeder birds the way the national monitoring scheme does"
date: "14 November 2026"
---

# In one sentence

A camera at a winter bird feeder, with a small model running on the Arduino UNO Q, that counts each species to the same rule Finnish bird monitoring already uses, and keeps the counts as open data.

# The problem

- Bird counts are an official measure of ecosystem health in the EU, and the numbers are bad: farmland birds are down 41% since 1990 (Eurostat 2026).
- Almost all of that monitoring happens in the breeding season. More than 80% of bird indicators use breeding-season data only [report, source 9].
- Finland's winter feeder data comes from volunteers who watch their feeder and fill in a form. The number of feeding stations is falling, mostly in southern cities.
- Smart feeders exist, but they take photos for their owner. They do not count to a standard method, and the data stays with the company.

# What the device does

1. Watches the feeder during daylight.
2. Finds and names each bird in the frame.
3. Keeps, for every species, the largest number seen at the same moment.
4. Logs how long it was actually watching, so a zero is a real zero.
5. Saves one photo with each record, so a person can check the identification.
6. Writes a file in the shape of the monitoring form, per half-month period.

# How it works

| Step | What happens | Where |
|---|---|---|
| Capture | A USB camera takes a frame every few seconds | UNO Q |
| Detect | A small object-detection model draws a box around each bird and names the species | UNO Q, no cloud |
| Filter | Only identifications above a confidence threshold count, matching the scheme's "surely identified species only" rule | UNO Q |
| Count | Largest number per species in one frame, per hour, then per day, then per half-month | UNO Q |
| Evidence | The best frame for each record is kept | UNO Q storage |
| Report | A table per half-month period, plus the watching hours | File export; a simple local web page for the demo |

The model has to be an object detector, not a plain image classifier, because the output is a count of birds in the frame.

## Example output

Made-up numbers, to show the format only.

| Period | Hours watched | Great tit | Blue tit | Tree sparrow | Greenfinch | Bullfinch |
|---|---|---|---|---|---|---|
| 1–15 November | 96 | 7 | 4 | 12 | 0 | 2 |
| 16–30 November | 104 | 9 | 5 | 15 | 1 | 3 |

## Species to start with

The eight most useful from the 2026 garden count: great tit, yellowhammer, blue tit, tree sparrow, bullfinch, blackbird, greenfinch, house sparrow. Tree sparrow against house sparrow is the hard pair. Squirrels and rats are worth a flag, because the scheme records mammals and rats are the main reason given for the fall in feeding stations.

## Training data

- Feeder-camera video from YouTube is the right kind of image. Use European streams, since the famous ones are North American.
- Label about 100–200 boxed examples per species. Let a ready-made "bird" detector draw the boxes so people only pick the species.
- Take frames from several cameras and test on one the model has never seen.
- Rights: the footage belongs to the uploaders. Prefer Creative Commons videos, and do not republish frames.

# Where the data goes

**Luomus feeding-station monitoring** (Finnish Museum of Natural History).

- Running since winter 1988–89, with more than 200 feeding stations.
- October to April, reported in half-month periods.
- The rule: the largest number of each species seen at once. Only surely identified species.
- Reported today on paper, in Excel or through a web service.

BirdLife's yearly garden count uses the same "largest number at once" rule for one hour. The next one is 30–31 January 2027.

**Not confirmed:** whether Luomus would accept counts made by a machine. Asking them is the most valuable next step.

# Where the impact comes from

- **More data.** The device watches every daylight hour all winter. A volunteer watches for a short while when they have time.
- **More consistent data.** The effort is the same every day and is logged, zeros are real, and each record has a photo. This is the claim to make. Do not claim it names species more accurately than a skilled volunteer, because a weekend model will not.
- **Accuracy is a solvable problem.** Identifying birds with AI already works in commercial products, so the method is proven. The prototype shows it running on a small board. State its measured accuracy on footage it has not seen, and say that more labelled footage is what raises it.
- **Data that decisions already rest on.** Governments and the EU use bird indices to judge ecosystem health [11]. The UK Government made its bird index a headline indicator and pledged to reverse farmland bird declines [10].
- **Scope.** This is knowledge about Finnish winter birds, one of several inputs to those indices. It is not a measure of the state of the planet.

# What the data can and cannot say

Based on the two reports in this folder.

**Can say**

- **How numbers change.** Repeated counts turned into a trend are the main working indicator, and the reports' authors prefer counts over species lists [10].
- **How the species mix shifts.** Counts mean more when species are sorted by habitat [10]. A feeder's visitors can be sorted the same way, for example forest species (willow tit, bullfinch, woodpecker) against town species (house sparrow, jackdaw, feral pigeon). This grouping is our own proposal and needs checking against how Luomus groups them.
- **Winter, with known effort.** Two stated weaknesses of today's indicators are that they are breeding-season only and that few account for how detectable birds are [9]. A device that watches fixed hours all winter addresses the first and takes a step toward the second.
- **Sudden events.** Feeder-type counts elsewhere have caught disease outbreaks and irruption years.

**Cannot say**

- **The state of an ecosystem from one feeder.** The indices in the reports combine national surveys over many sites and years [10, 11]. One feeder is one data point.
- **True abundance.** A feeder attracts birds, more so when natural food is scarce or it is cold. A rising count is not always good news [10]. Luomus says its own winter counts do not show true relative abundance.
- **Causes.** Bird monitoring is correlational [2]. The device shows that something changed, not why.
- **Anything about pollution, water quality or marine stocks.** Those bird signals need other methods.

# How it differs from what exists

| Existing counter | What it does | What ours adds |
|---|---|---|
| Volunteer with a form | Short, uneven watching; no photo | Every daylight hour, logged effort, photo evidence |
| Smart feeder (Bird Buddy, Birdfy) | Motion-triggered photo, identified in the company's cloud | A standard count, on the device, open data |
| Sound recogniser (BirdNET-Pi) | Detects that a species is present | Counts how many |
| BirdFeedR (same Arduino board, 2026) | Tells bird from not-bird | Species, counting and logging |

# Pros

- **A named destination.** The counting rule matches an existing national scheme exactly, so the data has somewhere real to go.
- **Constant effort and real zeros.** This is the one thing a machine does better than a volunteer.
- **Runs on the device.** No cloud, no subscription, no company. That is the Edge AI criterion and the brief's "not dependent on private companies" line.
- **Built to be many.** The unit is a board, a USB camera and a power supply, so it can be copied to many feeders cheaply. One feeder is a prototype of a network, not the whole idea.
- **A small problem.** Eight to fifteen species, not hundreds.
- **Training footage exists.** Feeder-camera video is the right kind of image.
- **Good timing.** The feeding season has started, and the national garden count is in January.
- **Brief fit.** "Local flora and fauna" is the challenge's first example, and wildlife is the EU's worst trend.
- **Known to work on the board.** An existing project runs a USB camera with Arduino App Lab on the UNO Q.

# Cons

- **The impact is indirect.** The device protects nothing by itself. Its effect comes through better data reaching the people who decide, so the pitch has to name a decision such data has fed. Impact is 30% of the score.
- **We will show one unit.** "Cheap and easy to install in many places" answers this only if we back it up: a parts cost per unit, and a model that works on a camera and background it has never seen.
- **Every site still needs a person and a socket.** Someone has to fill the feeder, and the unit needs mains power outdoors.
- **Acceptance is unconfirmed.** If Luomus will not take machine counts, the main argument weakens.
- **Crowded category.** Camera feeders are common, including on this exact board. Only the combination is new, so expect about half marks on creativity.
- **The camera sees less than a person.** The scheme counts a defined area around the feeder. A camera sees only its frame and will undercount ground feeders such as yellowhammer and blackbird.
- **Feeder bias.** Counts follow food and weather as well as population.
- **Accuracy.** A weekend model will confuse similar species, and wrong identifications are worse than none in monitoring data.
- **Labelling takes hours.** It is the real bottleneck, not training.
- **Feeding has its own risks.** Disease spreads at dirty feeders, and spilled seed attracts rats.
- **Camera not confirmed.** We still do not know whether the kit includes one.

# Demo plan

- **Main demo: recorded feeder video as the camera input.** A real camera filmed a real feeder, and that camera could be the one on the board. The board does everything else live: detection, counting, the table.
- **Say it is recorded.** "This is footage from a feeder, standing in for our camera" is an honest sentence and judges accept it.
- **Use footage the model was not trained on.** Otherwise the demo shows memory, not recognition.
- **Add one physical moment if a camera is available.** Twenty seconds of the board's own camera naming a bird photo a judge holds up. This is a hardware challenge, and a board with no sensor attached looks like software.
- **Optional, untested:** the kit's distance sensor on the perch can wake the model when a bird lands. That uses the board's microcontroller side and gives the demo a physical part even without a camera.

# Left for after the hackathon

Weatherproof housing, battery or solar power, low-light performance in midwinter, and frost on the lens. None of these is needed for a prototype.

# Fit with the judging criteria

| Criterion | Weight | Honest view |
|---|---|---|
| Technical implementation and Edge AI | 30% | Good, if the detector runs on the board and the counting logic is shown working |
| Environmental and social impact | 30% | Middling to good. Depends on naming Luomus, naming a decision the data feeds, and backing the "many units" claim |
| Creativity | 20% | About half. The twist is the protocol, not the camera |
| Working prototype and demo | 20% | Good, if the board processes unseen footage live and we say the footage is recorded |

# Next steps

1. Confirm the kit has a camera, or get a USB webcam.
2. Email Luomus and ask whether automated counts could enter the feeding-station scheme.
3. Collect European feeder footage and label the first three species to test the pipeline end to end.
4. Build the counting logic and the half-month table before improving the model.
5. Work out the parts cost per unit, to back the "many units" claim.
6. Record a demo video early, in case the live demo fails.

# What has been checked

- **Checked by us on the source pages:** the Luomus scheme (start year, number of stations, season, counting rule), the date and rule of BirdLife's garden count, the existence of BirdFeedR on the UNO Q, and the farmland-bird figure in the Eurostat report.
- **Read only by a research subagent:** the fall in feeding stations and its link to rats, the species list from the 2026 garden count, Bird Buddy's data policy, and the studies on disease and irruptions.
- **From the two reports in this folder:** statements marked [2], [9], [10] and [11]. Only sources 9 and 10 were read there in full.
- **Our own proposal, unchecked:** the habitat grouping of feeder species.
