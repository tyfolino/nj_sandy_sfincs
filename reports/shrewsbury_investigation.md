# Why does the Shrewsbury River under-fill? — A re-investigation

**Model run:** `snapwave_tuned` (our premier Hurricane Sandy setup, current build)
**Date:** 2026-07-08, **revised 2026-07-10**, **resolved 2026-07-14**
**Covered here:** Workstreams A, B, C, D, F/I (diagnosis) → **J and K (the answer)**

> ## ⚠️ Read this first (2026-07-14)
>
> **The under-fill was a mass leak. The model was draining the estuary.**
>
> The active-cell mask cut the Navesink River in half mid-channel and put a *free-outflow
> boundary* — a drain — on a five-metre-deep tidal cross-section. **92.6% of all the water
> entering the estuary was flowing straight out of the domain.** Sealing it (a mask edit;
> no rebuild) **closes the mass balance and closes the under-fill**: the Shrewsbury
> high-water-mark bias goes from **−0.42 m to +0.11 m** and the gauge from 2.22 m to 2.69 m
> against an observed 2.94 m, *without moving the basins that never leaked.*
>
> **Everything below Workstream F was measured on the leaking model.** Those results are
> not wrong so much as void: every experiment in the campaign hard-links the same broken
> `sfincs.nc`, so the entire comparison matrix — Faber vs Galibier, the iteration sweeps,
> the clamp study, wind, friction, the narrows-width test — was asking why a leaking bucket
> would not fill. **Their null results are now *explained*, not *informative*, and none of
> them should be cited as physics.** Sections A–F are kept below as the record of how we got
> here. Jump to **Workstream J** for the discovery and **K** for the fix.

---

## The short version

Our Hurricane Sandy model got the open Atlantic coast and Sandy Hook Bay right, but the
water behind the Sea Bright barrier — the Shrewsbury and Navesink rivers — came in about
half a metre too low. We spent two months asking whether that was a channel error, a bad
yardstick, or real physics. We checked the channel (faithful), the yardsticks (sound), the
boundary forcing (correct), the wind (a null lever), the mesh resolution (invariant), the
friction (already at open-water values), and the wave solver's convergence. Every lever
came back null.

**The nulls were the clue, and we misread them for months.** They were not telling us the
estuary was near some structural ceiling. They were telling us **the basin had a hole in
it**, and you cannot fill a bucket by widening the tap.

The model's mask chopped the Navesink in half mid-channel and left a free-outflow boundary
on the cut — a drain, on open tidal water five metres deep, 2.8 km short of the river's
true head of tide. It ran **one-way out of the domain in 100% of timesteps, from the first
hour, never reversing**, and it emptied the estuary *before the storm even arrived*. At
Sandy's peak the bay stood 3.2 m higher than the river a few kilometres away — a head drop
no constriction can sustain for three days. Only a sink does that.

**Plugging it solved the problem.** The mass balance closes (92.6% of inflow unaccounted
for → −5.7%), the cut reverses with the tide instead of draining forever, the pre-storm
drawdown disappears, the over-damped tide halves its damping, and the half-metre under-fill
is replaced by a slight +0.2 m overshoot. Critically, it moves *only* the basin that
leaked: the south-coast bias is unchanged to four decimal places.

Two lessons are worth carrying out of this. First, **the defect was in infrastructure, not
physics** — a boundary condition, the kind of thing nobody thinks to suspect — which is
exactly why a rigorous, exhaustive elimination of every *physical* lever could run for two
months and find nothing. Second, the investigation was saved by an **accident**: a
bookkeeping exercise that refused to balance. We did not find this by looking for it. We
found it because we finally added the water up.

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

> **Update (2026-07-10) — B is unaffected by the later convergence finding, and
> reinforced by it.** Everything in Workstream B is read from the model's static channel
> tables (the subgrid file), which are built once from the survey and bathymetry. Those
> tables are byte-for-byte identical across every model version and solver setting we
> ran — so nothing about the wave-solver discovery in Workstream I touches B's verdict;
> it needs no re-run. And the convergence fix actually resolves a tension that used to
> sit between A and B. B said the deep channel conveys the surge faithfully; the fix
> then showed the surge peak really does get into the estuary once the waves are
> computed properly. The two findings now agree instead of pulling against each other.
>
> One boundary on B worth keeping in mind (unrelated to the solver): B confirmed the
> model faithfully reproduces the **2015 channel survey** — not that the survey itself
> captures the true channel width. Whether the surveyed channel is narrower than reality
> is a separate question, tested directly by the narrows-widening experiment (Workstream
> H).

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

> **Update (2026-07-10) — one of these three yardsticks changed its verdict.** The
> tools below are all still correct; the numbers were computed on our premier run,
> which we later found was using an under-converged wave solver (Workstream I). Re-running
> the same yardsticks on a properly converged model splits them cleanly into two kinds:
>
> - **The tidal range (§3) is robust.** It is a *pre-storm* measurement, taken before
>   the wave problem occurs and when waves are tiny, so it comes out essentially
>   identical (~half a metre of muting) on every version of the model. This result
>   stands exactly as written.
> - **The storm-peak yardsticks (§1 gauge crest, §2 high-water marks) do not.** Both are
>   peak measurements, and the convergence fix *raises* the modelled peak in the estuary.
>   On the converged run the Shrewsbury gauge crest goes from **0.67 m low to about
>   0.30 m high** — the deficit doesn't just shrink, it reverses. So the "everything runs
>   low" reading in §1–§2 was in part a numerical artifact, and the honest peak-side
>   story is "matched or slightly over," not "under-filled."
>
> The datum work (§1), the basin-splitting method (§2), and the wet-cell tidal metric
> (§3) are all still valid and reusable — it is the peak *values*, not the methods, that
> shift. The final peak numbers will be re-tabulated once we settle which converged run
> is the premier (pending the Workstream I cross-checks). The paragraphs below preserve
> the original 2026-07-08 numbers for the record, with the revised reading flagged.

### 1. The gauge crest — is the target elevation even right?

The historic flood crest at the Shrewsbury gauge is quoted as "11.73 ft," which we
convert to 2.935 m in our vertical datum. But *which* datum is the 11.73 ft measured
against? If we guessed wrong, the whole deficit shifts.

**Confirmed:** the National Weather Service gauge page for this site
([`sbin4`](https://water.noaa.gov/gauges/sbin4)) is explicitly published "in MLLW"
(mean lower low water). The USGS sensor feed is a *separate* record in a different
datum — easy to confuse, but we checked. So our conversion is correct and the
**2.935 m target holds.** (There was a tempting coincidence that would have doubled the
deficit if the datum were different; the "in MLLW" label rules it out.)

> **Revised (2026-07-10):** the 2.935 m *target* is confirmed and unchanged, but the
> −0.67 m *deficit* against it was measured on the under-converged run. On a converged
> run the modelled crest rises to about 3.24 m — roughly 0.30 m **above** the target
> rather than below it. The target datum is solid; the sign of the gap is not what it
> looked like.

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

> **Revised (2026-07-10):** the *method* here — splitting marks by hydraulic basin
> instead of pooling them — is the durable contribution, and it still isolates the
> estuary as the distinctive basin. But the −0.27 m estuary bias is a peak measurement
> taken on the under-converged run, so it moves with the gauge crest above (toward zero
> or slightly positive on a converged run). These per-basin biases will be re-tabulated
> on the final premier; treat the numbers as provisional and the basin *split* as the
> lasting result.

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

> **Update (2026-07-10) — this is the yardstick that survives, and it is now the
> headline of A.** Because the tidal range is measured *before* the storm, it is immune
> to the wave-solver problem that shifted §1 and §2: we get the same ~0.5 m of muting on
> the original run, on the converged run, and on the interference-wave run alike. So the
> over-damping of the tide is a genuine, version-independent feature of the model — and
> with the storm-peak deficit now reversing, it is the clearest remaining evidence that
> something real slows the water as it spreads across the marshy interior.

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

The three cleaned-up yardsticks originally told one story — everything runs low. The
2026-07-10 convergence finding splits that into two, and the split is more informative
than the original agreement:

| Measurement | Original (2026-07-08) | Revised reading (2026-07-10, converged solver) |
|---|:--:|---|
| Gauge flood crest | −0.67 m (low) | **≈ +0.30 m (slightly high)** — deficit reverses |
| High-water marks (estuary only) | −0.27 m (low) | moves toward zero / slightly high (re-tabulation pending) |
| Tidal range | −0.53 m (muted) | **−0.5 m (muted) — unchanged, version-independent** |

The peak-based rows moved because they were measured on an under-converged wave solver;
the tidal-range row did not move because it is a pre-storm measurement the solver problem
never touched. So the honest synthesis is now:

- The **storm surge peak** is delivered into the estuary correctly once the numerics are
  sound — matched or slightly over, not under. Workstream B explains *why* it can be: the
  channel is deep, smooth, and wide enough to convey it. B and the peak measurements now
  agree.
- The **tide** is nonetheless over-damped by about half a metre — a real,
  version-independent feature — as it spreads across the shallow, marshy interior. This
  is the durable "something's off in the estuary" signal, and it lives in the distributed
  intertidal geometry, not the main channel (B) and not the surge.

**What this means for next steps:**

- No grid rebuild for the channel — that lever is exhausted.
- Write up the validation using these three sharpened yardsticks (gauge crest,
  basin-split high-water marks, tidal range) rather than the blunt basin-wide flood
  extent — but **lead with the tidal range**, the one that holds up across model
  versions, and report the storm-peak numbers on the converged premier once it is settled.
- The **model's numerics turned out to matter more than expected** — the wave-solver
  convergence fix (Workstream I) was what reversed the peak deficit. Finalizing the
  converged premier is now a prerequisite for re-tabulating the peak-based validation.
- The remaining things worth testing are outside the channel: the **wind and boundary
  forcing** (Workstreams C and D) and the **model's numerics/physics** (the SFINCS
  upgrade and the wave-solver convergence, Workstreams F and I).

---

## Workstream C — Is water escaping out the north boundary?

### What we were worried about

The advisor raised a sharp question: the model's north/northwest edge (the Raritan
Bay / New York Harbor side) is an *open* water-level boundary. What if surge water
that should be piling into the estuary is instead **leaking out** that open edge —
draining away head that would otherwise push the tide up the Shrewsbury and Navesink?
If so, the under-fill would be a boundary artifact, not a conveyance problem, and
sealing the edge would fill the rivers.

### What we found — the boundary is a *source*, not a leak

We measured the actual net flow of water across that boundary line directly, using
the model's stored velocities. The result is unambiguous and points the opposite way
from the worry:

| Across the N/NW line (open run) | Value | Direction |
|---|:--:|---|
| Peak flow rate | 28,200 m³/s | **into** the bay (southward) |
| Total over the storm | 1.7 billion m³ | **net inflow** from the harbor |

Water flows **in** across that edge, strongest right at the surge peak — it does not
escape. This matches what we already knew about the forcing: the boundary is pinned to
the observed Battery water level (~3.4 m), which is *higher* than the under-filled
estuary, so physically it can only feed water toward the rivers, never drain them.

The practical consequence: **sealing the boundary removes real inflow rather than
plugging a leak.** That's the reverse of the escape hypothesis. The formal confirmation
is an A/B "wall" experiment — an otherwise-identical run with the north edge closed off.

### The wall experiment confirms it

The wall run has now finished. Closing the north edge does raise the estuary a little —
but only by shoving the whole bay to a physically impossible level:

| At the surge peak | Open run | Walled run | Change |
|---|:--:|:--:|:--:|
| Sandy Hook Bay | 3.15 m | **4.97 m** | +1.8 m (vs ~3.4 m observed) |
| Shrewsbury River | 2.27 m | 2.87 m | +0.6 m |

To buy 0.6 m in the river, the wall has to super-elevate the bay by 1.8 m — to nearly
5 m, about a metre and a half above what actually happened at Sandy Hook. In other
words, you can only fill the rivers this way by making the bay badly wrong. The wall is
a diagnostic, not a fix: it *quantifies* how much artificial head it would take to force
the rivers up, and confirms the boundary itself is not the cause.

### The verdict from C

The direct water budget and the wall experiment agree: the north boundary is delivering
water to the bay, not bleeding it away, so **the escape hypothesis is refuted** and the
boundary is not the deficit.

> **Audit note (2026-07-10).** Both C runs were checked against the wave-solver
> instability found in Workstream I. They are clean: they use the older (Faber) engine,
> which — unlike the newer Galibier engine — stayed well-behaved, with no runaway waves
> anywhere in the domain. C's headline flux finding is a water-*budget* number driven by
> the observed Battery boundary level; it barely depends on the wave physics at all, so
> it is robust and premier-independent — it stands as written. The one thing that shifts
> is the *framing*: C was posed as "what explains the under-fill?", and the convergence
> discovery has since put the very existence of a peak-time under-fill in question (a
> converged run slightly *overshoots* the estuary crest). So read C not as "the boundary
> doesn't cure the under-fill" but as the cleaner, premise-free statement it always was:
> **the north boundary is a source, not a leak.**

---

## Workstream D — Does more wind push the water up the rivers?

### What we were worried about

Storm surge in a shallow bay is largely wind-driven: the wind drags the water surface
and piles it up against the coast. If our model's wind drag were set too weak, the whole
bay-and-estuary system would sit low, and the rivers would under-fill for that reason
alone. Wind drag is a genuinely uncertain parameter, so it is a fair lever to test.

We ran two sensitivity cases that increase the wind drag coefficient by 20% and 30%
above our baseline — a deliberately generous bracket — and asked whether the extra push
lifts the estuary.

### What we found — wind is a null lever here

| Run | Wind drag | Shrewsbury peak | Change vs baseline |
|---|:--:|:--:|:--:|
| Baseline | ×1.00 | 2.223 m | — |
| More wind | ×1.20 | 2.225 m | +0.002 m |
| Even more wind | ×1.30 | 2.227 m | +0.004 m |

Cranking the wind drag up by nearly a third moves the Shrewsbury peak by **four
millimetres**. It is, to the precision that matters, no effect at all. (At Sandy Hook the
peak nudges very slightly *down*, not up.) The estuary level simply is not gated by how
hard the wind is pushing on the bay — the water is already being delivered to the estuary
mouth; more wind doesn't change what happens once it's there.

This dovetails with everything else: the barrier-side bay levels validate well already,
so there is no missing wind push to be found, and adding it doesn't help the rivers.

### The verdict from D

Wind-drag magnitude is not the lever. Like the boundary, it is crossed off.

> **Audit note (2026-07-10).** The wind runs were checked against the Workstream I
> instability and are clean (older Faber engine, no runaway waves). Because this is a
> before-and-after comparison sharing the same solver settings, the near-zero *difference*
> is robust even if the shared baseline itself later shifts to a converged premier. The
> one soft spot: wind also feeds the wave model, which is the part with the convergence
> issue — so if we want to be airtight we would re-confirm the null once against the
> converged engine, a cheap check. As with C, the *framing* softens (this was posed as a
> cure for an under-fill whose peak-time existence is now in question), but the result
> itself — **wind magnitude does essentially nothing to the estuary** — is premier-
> independent and stands.

---

## Workstream F — Upgrading the model engine (and why it matters for waves)

A newer release of SFINCS — **v2.4.0 "Galibier"** (June 2026) — reworks the wave physics
we had tried and set aside. Two changes matter here:

1. *"Improvements of the integrated SnapWave solver for wave breaking, and resulting
   wave-induced setup, on steeper coasts."* This is the substantive change for us. It is
   the most likely reason the infragravity experiment (below) is now stable — and, as it
   turned out, also the source of a new numerical wrinkle we had to chase down
   (Workstream I; see the caution below).
2. *"Fixed bug with wavemakers, with waves forced from the north"* — which affected an
   earlier wavemaker experiment.

> **Correction (2026-07-10).** An earlier draft of this section credited Galibier with
> *"Fixed bug in SnapWave IG source term implementation."* That is real, but it belongs
> to the **previous** release (v2.3.0 "Faber," Feb 2025) — the engine our premier run
> *already* used. So the IG blow-up we saw earlier was **not** simply that old bug, and
> Galibier is **not** stable-because-it-fixed-the-IG-source-term. Whatever cured the IG
> instability is one of Galibier's *other* changes, most plausibly the wave-breaking
> rework in (1). The corrected takeaway is unchanged in spirit — our old "IG is unstable"
> verdict deserves a fresh look on the new engine — but for the right reason.

We confirmed the new engine drops straight into our setup: the model's pre-computed
channel/marsh tables load without any rebuild, and a regression run (identical inputs,
new engine) reproduces our premier result closely enough to trust it.

**The infragravity re-test is encouraging.** On the new engine the bay infragravity wave
height is now a physical few centimetres — **stable, no blow-up** — where the old run
exploded to billions of metres. IG finally gets a *fair* test, and we can no longer be
accused of dismissing it on the strength of a known bug.

> **Caution (2026-07-10) — the new engine is not a free upgrade.** While validating
> Galibier we found it can produce isolated, unphysical wave spikes on steep coasts (a
> 250 m wave at the bay mouth) when the wave solver is left at its default iteration
> limit — the flip side of the very wave-breaking rework that helps elsewhere. Raising
> the solver's iteration budget largely cures it, but two different fixes disagree on the
> exact estuary level and neither fully eliminates the spikes, so we do **not** yet have a
> settled, converged premier on Galibier. This is now its own small investigation
> (Workstream I), and the peak-based validation numbers in Workstream A are waiting on its
> outcome. The IG stability result above is unaffected — that run was one of the clean
> ones.

---

## Workstream J — Where does the water actually come from? (and the accident)

J was meant to be bookkeeping. We drew two control lines — one across the Sea Bright
barrier, one across the Highlands throat where Sandy Hook Bay meets the estuary — and
added up the water crossing each, to settle an argument about whether the estuary fills
*through* the narrows or *over* the barrier.

The bookkeeping did not balance. It did not merely fail to balance; it failed
catastrophically. **Water came in through the throat — 3.72 × 10⁸ m³ of it — and only
2.8 × 10⁷ m³ of it was still in the estuary at the end. Ninety-two per cent of the inflow
had gone somewhere.**

You cannot argue with that. Water does not evaporate in a hydrodynamic model. Either we
were measuring wrong, or the model had a hole in it.

### The hole

It had a hole in it.

The model's active-cell mask **chops the Navesink River in half, mid-channel**, at
easting ≈ 580,670. The cells at the cut were assigned a *free-outflow* boundary — the
condition you use at the downstream end of a river, where water is supposed to leave and
never come back. Immediately west of the cut, the cells are switched off, but the
*bathymetry is still water*, running down to −5.6 m: the real Navesink continues for
another 2.8 km, past Red Bank, to the true head of tide at Swimming River Dam.

So the edge of our domain was **a five-metre-deep open cross-section of a tidal river with
a drain on it.**

The measurements are unambiguous. At the cut, the water ran **out of the domain at −0.82
m/s on average, peaking at −2.02 m/s, in 100% of timesteps, from the first hour, never
once reversing.** A real tidal cross-section reverses every six hours. And the model began
draining the estuary *before the storm arrived*: from a flat start it pulled the Navesink
down to **−1.48 m by 04:00 on 28 October**, two days before Sandy's peak, on a calm night.
At the peak, Sandy Hook Bay stood at +3.09 m while the Navesink sat at −0.15 m — **a 3.2 m
head drop across a few kilometres of open tidal water.**

That last number is the one that ends the argument. A constriction can *delay* a basin
filling. It cannot hold a basin three metres below the water pressing against it for three
days. Only a sink does that.

Two further cuts leak the same way: the western end of **Shark River**, and the
**north-west/Raritan corner**.

### Why this mattered far beyond one run

Every experiment in this campaign was staged by hard-linking **the same `sfincs.nc`**.
Faber, Galibier, every iteration-count, clamp, wind, friction, dredge and mesh-refinement
arm — all of them inherited the leak.

Which retrospectively explains the single most frustrating feature of this whole
investigation: **the wall of null results.** Widening the narrows did nothing. Dredging did
nothing. Refining the mesh to 12.5 m did nothing. Wind did nothing. None of them were
wrong, and none of them were badly executed. *You cannot fill a bucket by widening the tap
when the bucket has a hole in it.*

It also explains the over-damped tide (A3): a continuously-draining basin cannot build
tidal amplitude. And it explains why the bias was **basin-selective** — why only the
estuary was low while Sandy Hook Bay and the open coast validated fine. Those basins have
tidal prisms of order 10⁹ m³; a leak barely dents them. The estuary's *entire tidal swing*
is 3.8 × 10⁷ m³ — **the leak was ten times its whole tidal signal.** The only basin small
enough to be drained dry by the hole was the only basin that was low.

---

## Workstream K — Plugging it

The fix required **no rebuild**: the subgrid tables already cover all 547,267 faces,
including the 155,232 switched-off ones, so this is a mask edit and nothing more. We ran a
2 × 2 — two fixes, each with waves on and off:

- **`wall`** — turn the leaking outflow cells into ordinary water, so the domain edge
  reverts to SFINCS's default closed wall. This *under-represents* storage: it walls the
  river 2.8 km short of its true head of tide.
- **`extend`** — the wall, *plus* switching the dead-but-wet cells back on (flood-filled
  from the cut, so nothing isolated gets activated), putting the wall at the real head of
  tide and recovering ~2.5 km² of genuine tidal prism.

The pair was designed to **bracket** the answer: `wall` should undershoot, `extend` should
be about right. Predictions were written down before the runs.

### 1. Is the leak gone?

| | leaking premier | `wall` | `extend` |
|---|---|---|---|
| velocity at the cut | **−1.08 m/s** | −0.011 | −0.010 |
| flowed *out* in… | **100% of steps** | 96% | **51–53%** |
| Navesink on a calm night | **−1.48 m** | +0.02 | +0.09 |
| inflow unaccounted for | **92.6%** | −6.1% | **−5.7%** |
| head drop bay → estuary (peak) | **+2.12 m** | +0.36 | +0.44 |

Yes. The cut now **reverses with the tide** instead of draining one way forever, the
pre-storm drawdown is gone, and **the mass balance closes.**

### 2. Did it fill?

Comparing like with like — the premier's own physics, waves on:

| | gauge crest | Shrewsbury HWM bias | pooled RMSE |
|---|---|---|---|
| observed | **2.935 m** | 0 | — |
| leaking premier | 2.223 (−0.71) | **−0.42 m** | 0.696 |
| `wall` | 2.720 (−0.22) | +0.23 m | 0.586 |
| `extend` | 2.691 (−0.24) | +0.21 m | **0.574** |

**The under-fill is closed.** The systematic deficit that has driven this entire
investigation — −0.42 m on the high-water marks, −0.71 m at the gauge — is gone, replaced
by a slight *overshoot* of about +0.2 m. Pooled RMSE improves by 18%. The over-damped tide
(A3) improves in step: Shrewsbury's tidal-range damping more than halves, from 0.54 m to
0.24 m.

The remaining gauge error of −0.24 m is inside the ±0.3 m band we already attribute to
forcing noise, and the gauge is a post-event surveyed crest rather than a hydrograph, so it
cannot be pushed harder than that.

### 3. The test it had to pass

The leak was *estuary-local*. So a leak fix **must not move the basins that never leaked** —
if it did, we would be looking at a global re-tuning wearing a leak fix's clothes, and the
diagnosis would be wrong.

It passed. **South-coast bias: −0.0553 → −0.0553, unchanged to four decimals.** Sandy Hook
Bay: +0.038 → +0.030. The correction is precisely as spatially local as the diagnosis said
it had to be.

### 4. Two things we got wrong

**The bracket collapsed.** `wall` and `extend` agree to within 0.03 m on every metric. We
predicted `wall` would undershoot, because it discards 2.5 km² of real tidal prism. It
doesn't. **What mattered was sealing the hole, not where the wall goes** — a result worth
keeping, because it says the fix is robust to exactly where we draw the line.

**Workstream J's own partition was contaminated by the leak it discovered.** J concluded the
throat out-delivers the barrier 41-fold and the barrier is negligible. But the drain was
*sucking water through the throat*: on the sealed model, throat inflow collapses from
3.72 × 10⁸ to 4.3 × 10⁷ m³. With the premier's physics, the honest ratio is **5×, not 41×,
and the barrier contributes 8.6 × 10⁶ m³ — about 17% of the inflow, not a rounding error.**
The barrier term is ten times larger with waves on than off, which is wave-driven
overtopping of the Sea Bright revetment doing exactly what the earlier knife-edge analysis
predicted it would.

---

## An unrelated defect this turned up: Shark River Inlet is dammed

While re-deriving the tidal-range metric on the sealed model, Shark River behaved
strangely: its "tidal range" *halved*. It turned out the metric there was never measuring a
tide at all — it was reporting `max − min` of the model's monotonic spin-up drawdown.

Following that led somewhere worse. **The Shark River estuary never floods. In any run of
this entire campaign, including the premier, its peak water level is exactly +0.00 m — its
initial condition — while the ocean 1.8 km away reaches +2.9 m.** It does not rise one
centimetre during Hurricane Sandy.

The cause is the same one we already fixed once, in a different place. Marching the bed
elevation across the inlet, the seaward channel is real (−4 to −10 m) and the landward
channel is real (−2.7 to −4.3 m), and **between them the lowest point anywhere on the
cross-section is +0.57 m — above mean sea level.** Shark River Inlet carries the NJ Transit
Coast Line bridge, the Route 71 bridge and Ocean Avenue, and they are baked into the lidar
as a solid earthen dam. **It is the Rumson–Sea Bright bridge-as-dam, a second time.** The
only mask-connected path from the Shark gauge to the sea climbs out of the channel and runs
1.7 km *overland across Belmar's streets* at +3 to +5 m.

### Why nobody noticed for months

This is the part worth internalising, and it is not the answer we first reached for.

The obvious explanation would be that the model failed to flood Shark River and the
high-water marks caught it. They did not — **because the model floods Belmar and Avon
anyway, from the wrong direction.** The ocean overtops the beach and runs *overland* through
the streets, so the two Shark high-water marks come out **wet** (0.30 m and 2.39 m deep),
while the river channel a few hundred metres away sits at exactly +0.00 m. A high-water mark
records that water arrived. It cannot tell you *which way it came*. The model was getting
roughly the right answer in the right place by an entirely wrong pathway, and the
mark-by-mark score was blind to it.

On top of that, those are the only two marks in the basin and both are **quality 3**, below
the `qual <= 2` headline cut — so they were never scored at all, wet or dry.

And the one metric that *should* have caught a dead basin — the tidal range — was itself
broken. It computed `max − min` over the first 24 h, which at Shark was not a tide but the
model's monotonic **spin-up drawdown**:

    +0.00  −0.63  −0.86  −0.99  −1.06  …  −1.27  −1.27  −1.27

`max − min` of that is 1.27 m. Against an observed 1.82 m it looked like a plausible,
mildly over-damped tide. It was a basin draining to a standstill with **zero tidal
oscillation**, and the metric had no way to say so.

So Shark had **no working diagnostic at all**: its HWMs were excluded by quality, would have
read wet regardless, and its tidal range was measuring a transient. Three independent
instruments, none of them pointed at the thing that was broken.

**Fixed (Workstream N):** the tidal-range metric now removes the spin-up trend and refuses to
report a range for a series that never rises (`is_tidal=False`) — Shark now trips that flag in
every run, which is exactly the alarm that was missing. `shark_river` is now its own HWM basin
instead of hiding inside `south_coast`.

**Also fixed, though it turned out not to be the culprit here:** the HWM score only counted
marks the model actually floods (`head = wet & (qual <= 2)`), silently dropping dry ones — so
it *structurally rewarded failing to flood*, the mirror image of the MOTF POD flaw. That is a
genuine defect and dry marks are now scored against ground elevation. But it is worth being
precise: **no q<=2 mark is dry in any of these runs (`n_dry = 0`), so this flaw did not hide
Shark.** We initially blamed it, and that was wrong.

---

## Where this leaves the investigation

The estuary under-fill — the question this report was opened to answer — **is solved, and
the answer was a mass sink, not missing physics.**

That is a happier ending than the one we were heading for. The 5 July conclusion was that
the residual was a *distributed conveyance over-restriction near the structural ceiling of
the subgrid* — in other words, not a fixable knob, and the recommendation was to write up
the systematic elimination as the contribution. That was wrong, and it was wrong in the
most instructive way: **the elimination was sound, every excluded lever really was
excluded, and the reason nothing worked is that the defect was not on the list of things
anyone thought to check.** The boundary was never suspected because a boundary is
infrastructure, not physics.

What now needs redoing, honestly:

- **The premier must be re-established on the sealed domain.** Faber-vs-Galibier, the
  iteration sweeps, the clamp study, wind, friction, the narrows-width test — every one of
  those comparisons ran on a leaking bucket. Their null results are now *explained*, not
  *informative*, and none of them can be cited as physics.
- **Fix the Shark River Inlet dam**, the same way the Rumson–Sea Bright causeway was fixed:
  carve the surveyed channel through it.
- **Fix the HWM metric** so that a mark the model fails to flood counts as an error.
- **Re-examine the +1.03 m Atlantic-oceanfront bias**, which the leak fix left standing (it
  was +0.73 m before) and which is now the largest remaining error in the model.

*Workstreams I, H and E — convergence, narrows width, infragravity — are superseded as
written. They were all asking why a leaking bucket wouldn't fill.*
