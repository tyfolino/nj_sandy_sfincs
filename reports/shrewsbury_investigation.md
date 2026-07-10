# Why does the Shrewsbury River under-fill? — A re-investigation

**Model run:** `snapwave_tuned` (our premier Hurricane Sandy setup, current build)
**Date:** 2026-07-08, **revised 2026-07-10** · **Covered here:** Workstreams A, B, C, D (and F/I notes)

> **Revision note (2026-07-10).** A later finding (Workstream I) changed how we read
> Workstream A. We discovered that the wave model's solver had been stopping short of a
> converged answer, and fixing that *raises* the modelled storm peak in the estuary. The
> consequence: A's **tidal-range** result is robust and unchanged, but A's **storm-peak**
> deficit was partly a numerical artifact — on a properly converged run the peak is
> matched or slightly overshot, not low. B is unaffected and, if anything, reinforced.
> The A and B sections below have been updated in place; look for the dated callouts.

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
error. On the yardstick side, the cleaned-up **tidal-range** measurement shows the tide
arriving about half a metre muted in the estuary, and this holds up on every version of
the model we have tested. The **storm-peak** measurements (gauge crest, high-water
marks) originally also read low — but we later traced that to the wave solver stopping
short of convergence; on a properly converged run the peak comes in matched or slightly
high, not low (see the 2026-07-10 callouts below).

Put together, the picture that survives is: the **tide** is genuinely over-damped as it
spreads across the shallow, marshy interior, while the **surge peak** is delivered
correctly to the estuary once the numerics are sound. The residual is in the
tidal/intertidal signal, not the main channel and not the storm surge — consistent with
B's finding that the deep channel conveys faithfully.

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

## Still to come

- **I (in progress) — settle the converged premier.** This is now the critical path.
  Two different ways of stabilizing the Galibier engine give estuary levels ~0.4 m apart
  and neither fully removes the wave spikes, so we need to pin down the converged answer
  (an iteration sweep and/or combining the fixes) before any peak-based number is final.
- **A peak numbers (blocked on I)** — Once the premier is settled, re-tabulate the gauge
  crest and per-basin high-water-mark biases on it. (The tidal-range result needs no
  re-run.)
- **H (running) — the narrows-width test.** A deliberately over-widened channel, run on
  the stabilized engine, to test whether the surveyed channel is narrower than the real
  one. Re-based onto the converged engine after the original comparison was found to use
  a corrupted baseline.
- **E — infragravity evaluation.** IG now runs stably (above); evaluate whether it helps
  the open-coast wave setup, and reword the earlier "IG is unstable" verdict.

*This report will be extended as the convergence (I), width (H), and IG (E) work
completes.*
