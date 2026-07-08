# Why does the Shrewsbury River under-fill? — A re-investigation

**Model run:** `snapwave_tuned` (our premier Hurricane Sandy setup, current build)
**Date:** 2026-07-08 · **Covered here:** Workstreams A & B (C and D to follow)

---

## The short version

Our Hurricane Sandy model gets the open Atlantic coast and Sandy Hook Bay right, but
the water behind the Sea Bright barrier — the Shrewsbury and Navesink rivers — comes
in about half a metre too low. The question this round: is that a *fixable* problem in
how we represent the river channel, or is it a soft comparison against unreliable
gauges, or is it something real and built into the estuary's physics?

We attacked it two ways, both on the model we already have (no re-running the
expensive grid build):

- **Workstream B** looked *inside* the model at how it represents the river channel
  through the narrows — is the channel accidentally too shallow, too rough, or too
  narrow?
- **Workstream A** cleaned up the *yardsticks* — the gauge, high-water-mark, and tidal
  measurements we judge the model against — so we can trust the verdict.

**What we found.** The model's channel is faithful: it is as deep, as smooth, and as
wide as the real surveyed channel — so the under-fill is **not** a fixable channel
error. And once the yardsticks are cleaned up, **three independent measurements agree**
the estuary really does come in low. Put together: the under-fill is real, it is
confined to the water behind the barrier, and it is not a knob we can simply turn. That
confirms — with much better evidence — what we concluded on 2026-07-05.

---

## Workstream B — Is the model's river channel built correctly?

### What we were worried about

The model doesn't resolve the river channel cell-by-cell. Instead it uses a *subgrid*
method: within each coarse grid cell it keeps a small lookup table describing how deep
and how smooth the flow is at that spot, computed from fine-resolution bathymetry. The
worry was that this lookup table might quietly under-represent the channel — making it
too shallow, too rough, or too pinched — which would choke the surge as it tries to
push up the rivers. If so, that would be fixable: improve the bathymetry, rebuild.

To check, we had to read those lookup tables exactly where the real channel runs
through the narrows, and compare them against the actual 2015 channel survey (eHydro).
The tricky part is that the tables are stored in the model's own internal order, with
no coordinates attached. We reconstructed that ordering and confirmed it lines up
perfectly (all 1,355,381 entries), so every table entry could be placed on the map and
matched to a survey depth.

The reusable tool that does all this is
[`scripts/probe_subgrid_conveyance.py`](../scripts/probe_subgrid_conveyance.py).

### What we found

**The channel is exactly as deep as it should be.** Along the surveyed channel, we
asked: at a given water level, how much flow depth does the model actually use, versus
the ideal "water level minus real riverbed"? The answer is a dead-on match at every
stage, right up through Sandy's peak surge:

| Water level | Flow depth the model uses | Ideal (level − riverbed) | Match |
|---:|---:|---:|:--:|
| 0 m | 2.9 m | 3.0 m | ✓ 100% |
| 1 m | 3.9 m | 4.0 m | ✓ 100% |
| 2 m | 4.9 m | 5.0 m | ✓ 100% |
| 3 m (surge) | 5.9 m | 6.0 m | ✓ 100% |

The deep-channel carve we added earlier (to defeat the Rumson–Sea Bright bridge, which
sits in the elevation data like an earthen dam) is faithfully present: the model's
deepest channel point matches the survey to within 3 cm.

**The channel is as smooth as it should be.** Roughness (Manning's *n*) in the channel
comes out at 0.017 — clean open water — while the surrounding marsh comes out at 0.038,
a realistic salt-marsh value. The marsh roughness is *not* bleeding into the channel
and slowing it down artificially.

**The inlet is not a bottleneck.** Where the estuary connects to Sandy Hook Bay:
- the river reaches are 150–230 m wide, which is 12–18 grid cells across — plenty of
  resolution;
- the connecting throat has no shallow sill — the bed stays below −9.6 m the whole way
  through, scoured to −13 m, with hundreds of deep flow paths across every section;
- the roughness right in the throat is 0.017 (clean) at both low tide and peak surge.

We also ruled out channel *meandering* as a cause: the grid tends to straighten a
winding channel, which would make it flow *more* easily, not less — so it can't explain
water coming in too low.

### The verdict from B

The model's channel is faithful — deep enough, smooth enough, wide enough. **The
under-fill is not a channel-representation error, so there is nothing to fix here and
no reason to rebuild the grid.**

### A useful side-discovery

While digging, we noticed the interior tide gauges in the model are sitting on dry
ground: the model cells they landed on have bed elevations of +1.4 m, +1.3 m, and
+2.0 m — above the normal tide range — so those cells are dry most of the time and the
gauge simply reports the ground elevation. Any tidal measurement read straight off
those gauge points would be meaningless. This directly shaped how we built the tidal
metric in Workstream A (we sample genuinely wet channel cells instead).

---

## Workstream A — Can we trust the yardsticks?

Before leaning on any verdict, we hardened the three ways we measure the under-fill.
All of this now lives in [`nj_sfincs/validate.py`](../nj_sfincs/validate.py).

### 1. The gauge crest — is the target elevation even right?

The historic flood crest at the Shrewsbury gauge is quoted as "11.73 ft," which we
convert to 2.935 m in our vertical datum. But *which* datum is the 11.73 ft measured
against? If we guessed wrong, the whole deficit shifts.

**Confirmed:** the National Weather Service gauge page for this site
([`sbin4`](https://water.noaa.gov/gauges/sbin4)) is explicitly published "in MLLW"
(mean lower low water). The USGS sensor feed is a *separate* record in a different
datum — easy to confuse, but we checked. So our conversion is correct and the
**2.935 m target and the −0.67 m model deficit hold.** (There was a tempting
coincidence that would have doubled the deficit if the datum were different; the "in
MLLW" label rules it out.)

### 2. The high-water marks — the average was hiding the problem

There are 31 surveyed Sandy high-water marks in the area. Lumped together, the model
matches them with an average error near zero (−0.05 m) — which looks like the model is
fine. But that average blends two very different places: the wave-exposed ocean front,
where the model runs slightly *high*, and the sheltered estuary behind the barrier,
where it runs low. The two cancel out.

So we split the marks into hydraulic basins and looked at each separately:

| Where the marks are | # marks | Average model error |
|---|:--:|:--:|
| *(all lumped together — misleading)* | 30 | −0.05 m |
| Atlantic ocean front | 3 | **+0.48 m** (model high) |
| **Shrewsbury / Navesink (behind the barrier)** | 10 | **−0.27 m** (model low) |
| Open Sandy Hook Bay | 2 | +0.03 m |
| South coast (Shark River / Belmar) | 4 | +0.06 m |

The behind-the-barrier estuary is the **only** place the model runs low. Everywhere
else it's spot-on or slightly high. The high-water marks, read properly, independently
confirm the under-fill — the pooled average had simply washed it out.

### 3. The tidal range — the tide comes in muted

Separate from the storm peak, we can check how far the water rises and falls on a
normal tide before the storm. Using the genuinely-wet channel cells (not the dry gauge
points from B), over the same pre-storm window as the observations:

| Gauge | Model tide range | Observed tide range | Model is short by |
|---|:--:|:--:|:--:|
| Shrewsbury | 0.84 m | 1.37 m | 0.53 m |
| Shark River | 1.27 m | 1.82 m | 0.55 m |

The tide genuinely arrives muted in the model — about half a metre short of reality —
*even though* Workstream B showed the deep channel conveys perfectly. That's a strong
hint the damping is spread out across the shallow, marshy intertidal areas, not
concentrated in the main channel.

### 4 & 5. Two framing fixes

- **The gauge is on a bank, not in the channel.** The Shrewsbury gauge point landed on
  a cell whose bed is +1.4 m — a bank, not the −4 m channel it was meant to sit in. We
  now flag this. It does *not* bias the storm peak (at peak the water surface is
  continuous across the bank and channel), but it *does* ruin a tide-range reading from
  that point — which is exactly why the tidal metric above uses channel cells instead.
- **The Sandy Hook gauge died mid-storm.** It failed on the rising tide, before the
  peak, so comparing the model's peak to the gauge's last reading unfairly makes the
  model look 0.31 m low. We now report both honestly: the fair pre-failure comparison
  (−0.31 m against a truncated record) *and* the model's true peak of 3.15 m, which the
  dead gauge never lived to see.

---

## Putting it together

Three independent yardsticks, each now cleaned up, tell the same story:

| Measurement | Under-fill | Based on |
|---|:--:|---|
| Gauge flood crest | −0.67 m | surveyed peak, datum confirmed |
| High-water marks (estuary only) | −0.27 m | 10 marks, basin-isolated |
| Tidal range | −0.53 m | wet channel cells vs USGS gauges |

And Workstream B shows the *cause* is not the model's channel: the channel is deep,
smooth, and wide, matching the survey. The best reading is that the surge and tide are
delivered correctly to the mouth of the estuary but get **over-damped as they spread
across the shallow, marshy interior** — a real, distributed feature, not a single
knob we can turn.

**What this means for next steps:**

- No grid rebuild for the channel — that lever is exhausted.
- Write up the validation using these three sharpened yardsticks (gauge crest,
  basin-split high-water marks, tidal range) rather than the blunt basin-wide flood
  extent.
- The remaining things worth testing are outside the channel: the **wind and boundary
  forcing** (Workstreams C and D, coming next) and the **model's numerics/physics**
  (the SFINCS upgrade, later).

---

## Still to come

- **C** — Test whether water is escaping out the north/northwest boundary (a
  water-budget check plus a "wall off the boundary" experiment).
- **D** — Test whether stronger wind would lift the estuary (±20–30% wind, and a
  sharper hurricane wind field).
- **F → E** — Upgrade SFINCS to the new version and re-test the infragravity-wave
  physics on a clean build.

*This report will be extended as C and D complete.*
