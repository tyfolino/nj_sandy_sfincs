# Experiment naming convention

**This repo is `v1_monmouth` and is FROZEN** as the record of the sealed-premier campaign.
The domain never varies here, so experiment names carry no domain prefix. The multi-domain
repo (`~/nj_coast_sfincs`) prefixes every name with its `NJ_DOMAIN` key instead — see
"Cross-repo" at the bottom.

## The rules

1. **The sealed 2×2 keeps factorial names** — `<solver>-<waves>`. Those four arms are one
   designed experiment (container × waves on/off) and read best as a block.
2. **Everything after it is a DELTA from the premier**, named `<family>-<value>`:
   - `wave-…`  the SnapWave configuration
   - `tide-…`  the water-level boundary forcing
   - `solver-…` the SFINCS container
   - `mask-…`  the SFINCS active mask / domain extent
   - `bed-…`   bathymetry / subgrid parameters
3. **A union is its parents joined by `+`**, in alphabetical order so there is exactly one
   spelling: `wave-deep30+tide-shift` is unambiguously `wave-deep30` × `tide-shift`.
4. **`premier` is a role, not a name.** It is a suffix on the arm currently adopted as
   baseline, so the adopted arm is identifiable without knowing the campaign's history.
5. **Retired arms keep their historical names**, marked ⛔. Their value is archival; renaming
   them would rewrite the record of what was actually run.
6. **`v1`/`v2` are reserved for DOMAIN and nothing else.** A revision of a *forcing* never
   gets a bare version number. (The old `phaselag_composite_v2` violated this — its `v2` was
   a forcing revision, which collided with `coast_v2` the domain.)

## Mapping — old → new

### Live arms

| legacy name | current name | what it varies |
|---|---|---|
| `sealed_faber_waves` | **`faber-waves-premier`** ⭐ | the adopted baseline |
| `sealed_faber_nowaves` | `faber-nowaves` | waves off |
| `sealed_galibier_waves` | `galibier-waves` | `sfincs-cpu.sif`, `snapwave_gammax=2` |
| `sealed_galibier_nowaves` | `galibier-nowaves` | both of the above |
| `sealed_igwaves_wind` | `wave-ig` | `snapwave_igwaves 0 → 1` |
| `snapwave_deep` | `wave-deep30` | SnapWave mask DECOUPLED, boundary → −30 m |
| `phaselag_shift` | `tide-shift` | Battery tide advanced +24 min, 2 support points |
| `snapwave_deep_phaseshift` | `wave-deep30+tide-shift` ⭐ | union of the two above |

### ⛔ SUPERSEDED — off the sealed domain, never concluded

| legacy name | current name | what it varies |
|---|---|---|
| `sealed_bdepth_m15` | `mask-zmin15` ⛔ | SFINCS active mask extended to ≈−15 m |
| `sealed_bdepth_m20` | `mask-zmin20` ⛔ | SFINCS active mask extended to ≈−20 m |

**Run 2026-07-15** as Phase 2 "Workstream M — boundary-depth sweep" (SLURM 58185237/38/39),
staged by `scripts/setup_boundary_depth.py` (NOT by `run_experiments.py`, which is why they
have no `EXPERIMENTS` entry). **The workstream was launched and never concluded**: no report
CSV, no recorded verdict, no ⛔ until now.

**Superseded by `wave-deep30`**, which pursues the same goal — get the wave boundary into
water deep enough for ERA5's Hs to be admissible — but extends *only* `snapwave_mask`,
leaving the SFINCS mask, the surge boundary and the seal intact. Strictly the better
instrument for that question.

**`bdepth` meant BOUNDARY DEPTH of the SFINCS mask, not the wave boundary** — a natural
misreading, and the reason these were briefly misfiled under `wave-`. They extend
`mask_zmin` seaward: 21,747 / 76,294 cells go inactive→active down to −16.8 m / −21.3 m,
plus new water-level boundary cells (0→2) and old boundary cells demoted to interior (2→1).

⚠️ **Because that MOVES THE WATER-LEVEL BOUNDARY, it changes `sha(z,mask)` by construction**
(`09f81bf7…` / `1d525831…` vs the sealed `45f4f74c…`), so `premier.py` reports them
UNRECOGNISED and **their HWM/CSI numbers can never be compared to the premier's.** Same face
and edge count, different domain — the trap this fingerprint exists to catch.

They are the **coupled predecessor of `wave-deep30`**: same goal (get the wave boundary into
deeper water), opposite method. `mask-zmin*` extends the whole SFINCS domain and drags the
surge boundary with it; `wave-deep30` extends only `snapwave_mask` and leaves the SFINCS
mask, the surge boundary and the seal untouched — which is precisely why `wave-deep30` is
comparable and these are not.

⚠️ **DO NOT TRUST THEIR CACHED FLOODMAPS.** Their only scoring event, 2026-07-16, IS the
incident that exposed the floodmap truncation bug — `plots.py` records `sealed_bdepth_m20`
scoring "0.72 from a complete raster, then 0.00 from a 4 MB stub of the same run". The tifs
in those dirs date from that day, before the atomic write landed. Current ratios are 0.165
and 0.177 against a healthy 0.11–0.16 (high, not stub-short — consistent with a larger
active domain flooding more), but **`plots.py` is explicit that file size cannot separate a
good cache from a bad one.** If you ever score these, pass `force=True` to rebuild.

Kept rather than deleted: they cost nothing, they are the only record of the coupled
approach, and they document why decoupling was the right instrument.

### Retired — names unchanged, do not re-run

| name | why retired |
|---|---|
| `phaselag_gtsm` | ⛔ GTSM tide ~34% under-amplitude region-wide |
| `phaselag_composite` | ⛔ fixed phase, over-forced the coast (bias +0.73) |
| `phaselag_composite_v2` | ⛔ superseded by `tide-shift`; run dir DELETED |
| `snapwave_deep_composite_v2` | ⛔ 2×2 interaction evidence only; superseded by `wave-deep30+tide-shift` |
| `baseline_no_waves`, `wind_waves`, `snapwave_tuned`, `snapwave_tuned_wavemaker`, `igwaves`, `igwaves_wind`, `wavemaker`, `phaselag_battery`, `phaselag_shblend` | pre-rebuild arms on the leaking `_template`; no run dirs |

### Templates — deliberately NOT renamed

`_template_sealed` (the only legal staging source) and `_template` (the pre-rebuild,
leaking-Navesink / dammed-Shark build) keep their names. `premier.py` already guards the
distinction with `SEALED_TEMPLATE` / `LEGACY_TEMPLATE` and errors with *"Stage from
`_template_sealed`, not `_template`"*. `_template_sealed` is referenced from
`hpc/stage_and_run_sealed.slurm` and `scripts/setup_sealed_premier.py`; renaming the guarded
path to gain what the guard already provides is a bad trade.

## Scored results (verified 2026-07-27, full-raster path, all on the sealed domain)

| arm | HWM bias | HWM RMSE | within 0.5 | SH lag | CSI |
|---|---|---|---|---|---|
| `faber-waves-premier` | 0.318 | 0.480 | 73.7% | 17.6 | **0.706** |
| `tide-shift` | 0.302 | 0.466 | 73.7% | **−0.1** | 0.701 |
| `wave-deep30` | 0.285 | 0.463 | 78.9% | 17.8 | 0.687 |
| `wave-deep30+tide-shift` | **0.273** | **0.449** | 78.9% | 0.1 | 0.684 |

The two knobs are ~additive (RMSE 100%, bias 91%). The union is the best **level** model and
the worst **extent** model — see `project_snapwave_decoupling` memory for the trade.

## Cross-repo

`~/nj_coast_sfincs` hosts several domains, so names there are `<domain>/<arm>` using the
`DOMAINS` registry keys verbatim (the first token IS the `NJ_DOMAIN` value):

```
v1_monmouth/faber-waves-premier
v2_barnegat/faber-waves-premier
v2_barnegat/wave-deep30+tide-shift
```

Domain keys are named for how far south they reach, since that is the only thing the staged
march to Cape May changes: `v1_monmouth` (→ lat 40.15) ⊂ `v2_barnegat` (→ lat 39.70) ⊂ …
The storm is NOT in the domain name — it is constant across every run here, and if it ever
varies it belongs on its own axis.
