"""Generate a self-contained HTML report of the experiment sweep.

One page an advisor can open in any browser with no environment: a metrics table
(best value per column highlighted) + a flood-map thumbnail per experiment +
the Sandy Hook Bay wave numbers. Images are embedded as base64 data URIs so the
file is fully portable (email it, drop it on a share).
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
import pandas as pd
import rioxarray  # noqa: F401

# Columns where a HIGHER value is better (skill up); everything else lower/abs.
HIGHER_BETTER = {"motf_csi", "motf_pod", "hwm_within0.5", "shb_hm0_mean", "shb_hm0_max"}
ABS_BEST = {"gauge_peak_err_m", "hwm_bias_m"}  # closest to zero is best


def _thumb(tif: Path) -> str | None:
    """Render a flood-map GeoTIFF to a small PNG data URI (or None if missing)."""
    if not tif.exists():
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    da = rioxarray.open_rasterio(tif, masked=True).squeeze(drop=True)
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    da.where(da > 0.05).plot.imshow(ax=ax, vmin=0, vmax=5, cmap="viridis",
                                    add_colorbar=True, cbar_kwargs={"label": "depth [m]"})
    ax.set_aspect("equal")
    ax.set_title("")
    ax.set_xlabel("")
    ax.set_ylabel("")
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=90)
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _fmt(col: str, v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}"
    return str(v)


def _best_mask(df: pd.DataFrame) -> dict[str, str]:
    """Experiment name of the best value per column (for highlighting)."""
    best = {}
    for col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().sum() == 0:
            continue
        if col in ABS_BEST:
            best[col] = s.abs().idxmin()
        elif col in HIGHER_BETTER:
            best[col] = s.idxmax()
        else:  # lower is better (RMSE, FAR, dry count)
            best[col] = s.idxmin()
    return best


def generate_html_report(metrics_df: pd.DataFrame, exp_root: Path,
                         out_path: Path | None = None) -> Path:
    exp_root = Path(exp_root)
    if out_path is None:
        out_path = exp_root / "report.html"
    df = metrics_df.copy()
    best = _best_mask(df)
    floodmaps = exp_root / "floodmaps"

    # Metrics table
    cols = list(df.columns)
    head = "".join(f"<th>{c}</th>" for c in cols)
    rows = []
    for name in df.index:
        cells = []
        for c in cols:
            hi = " class='best'" if best.get(c) == name else ""
            cells.append(f"<td{hi}>{_fmt(c, df.loc[name, c])}</td>")
        rows.append(f"<tr><th class='rowh'>{name}</th>{''.join(cells)}</tr>")
    table = (
        f"<table><thead><tr><th>experiment</th>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

    # Flood-map gallery
    cards = []
    for name in df.index:
        uri = _thumb(floodmaps / f"{name}_hmax_lev3.tif")
        img = f"<img src='{uri}'>" if uri else "<div class='noimg'>no flood map</div>"
        csi = df.loc[name].get("motf_csi", float("nan"))
        shb = df.loc[name].get("shb_hm0_max", float("nan"))
        cards.append(
            f"<figure><figcaption>{name}</figcaption>{img}"
            f"<div class='cap'>CSI {_fmt('motf_csi', csi)} · "
            f"bay Hm0max {_fmt('shb_hm0_max', shb)} m</div></figure>"
        )
    gallery = "<div class='gallery'>" + "".join(cards) + "</div>"

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>NJ Sandy — wave sensitivity experiments</title>
<style>
 body{{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:2rem auto;max-width:1100px;color:#1a2330;padding:0 1rem}}
 h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:2rem;border-bottom:1px solid #dce3ec;padding-bottom:.3rem}}
 table{{border-collapse:collapse;width:100%;font-size:13px;overflow-x:auto;display:block}}
 th,td{{border:1px solid #dce3ec;padding:.4rem .55rem;text-align:right;white-space:nowrap}}
 thead th{{background:#f3f6fa;position:sticky;top:0}} .rowh,td:first-child{{text-align:left}}
 .best{{background:#e7f6ec;font-weight:600;color:#127a3a}}
 .gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem;margin-top:1rem}}
 figure{{margin:0;border:1px solid #dce3ec;border-radius:8px;padding:.6rem;background:#fff}}
 figure img{{width:100%;height:auto;border-radius:4px}}
 figcaption{{font-weight:600;margin-bottom:.4rem}} .cap{{font-size:12px;color:#5a6472;margin-top:.3rem}}
 .noimg{{height:220px;display:flex;align-items:center;justify-content:center;color:#9aa4b2;background:#f6f8fb}}
 .note{{color:#5a6472;font-size:13px}}
</style></head><body>
<h1>NJ Sandy — SnapWave sensitivity experiments</h1>
<p class='note'>Hurricane Sandy (2012-10-29). Metrics vs the Sandy Hook gauge, USGS High Water Marks,
and the FEMA MOTF flood extent. Green = best across experiments. <code>shb_hm0</code> = SnapWave Hm0
in the Sandy Hook Bay lee (the "did waves reach the bay?" diagnostic).</p>
<h2>Skill metrics</h2>
{table}
<h2>Flood-extent comparison</h2>
{gallery}
</body></html>"""
    out_path.write_text(html)
    return out_path
