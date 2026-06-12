# Amarel bootstrap — from fresh account to Claude Code running on the cluster

Goal of this runbook: get **miniforge + Node + Claude Code** live on an Amarel login
node, so a cluster-side Claude session can then drive the SFINCS setup (env, data,
Singularity, Slurm) directly. Phase 2 (the actual SFINCS port) is done *with* that
cluster-side Claude, not from this file.

> ⚠️ Items marked **[verify]** are typical-Amarel assumptions — confirm them in the
> Phase 0 recon rather than trusting them blind. Module names and quotas drift.

---

## Pre-reqs (from your laptop)
- Off-campus → connect the Rutgers VPN (`vpn.rutgers.edu`), and have **Duo** ready.
- `ssh <netid>@amarel.rutgers.edu` (NetID password + Duo push).
- Alternatively the web portal: **ondemand.hpc.rutgers.edu** (shell + file browser in a browser).

---

## Phase 0 — Recon (you don't know what's there yet; inventory it)
Paste this whole block on the login node and send me the output — it tells us module
names, container runtime, storage, and whether the login node has internet:

```bash
echo "== host/OS =="; hostname; cat /etc/os-release | head -2
echo "== you =="; whoami; groups
echo "== storage + quota =="; echo "HOME=$HOME"; ls -ld /scratch/$USER 2>/dev/null; \
  quota -s 2>/dev/null; df -h $HOME /scratch/$USER 2>/dev/null
echo "== modules: container runtime =="; module avail 2>&1 | grep -iE "singularity|apptainer"
echo "== modules: node/conda/git =="; module avail 2>&1 | grep -iE "node|conda|miniforge|anaconda|git-lfs"
echo "== login-node internet (needed for Claude auth + pulls) =="; \
  curl -sI https://api.anthropic.com 2>&1 | head -1; \
  curl -sI https://github.com 2>&1 | head -1
echo "== compute-node internet? check after; often BLOCKED -> pull on login node =="
```

Key things we're learning:
- **Where the 29 GB elevation data goes.** HOME quota is usually small → data + miniforge + the SFINCS model go in **`/scratch/$USER`** (large, but periodically purged — keep `data/` reproducible from `scripts/download_*.py`). **[verify]**
- **Container runtime** = `singularity` or `apptainer` (the newer name). SFINCS runs here, since Docker daemons aren't allowed on HPC.
- **Login node has internet** (for Claude auth + image/data pulls); **compute nodes often do not** → always pull containers/data on the login node.

---

## Phase 1 — miniforge + Node + Claude Code

### 1. miniforge (install into scratch if HOME quota is tight)
```bash
cd /scratch/$USER   # or $HOME if quota allows
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p /scratch/$USER/miniforge3
/scratch/$USER/miniforge3/bin/conda init bash
source ~/.bashrc
```

### 2. Node (for Claude Code — needs Node 18+)
Prefer a module if recon found one; otherwise get it from conda:
```bash
# option A: module load node          # if Phase 0 showed a node module  [verify]
# option B (reliable):
conda create -n tools -c conda-forge nodejs -y
conda activate tools
node --version    # expect >= 18
```

### 3. Claude Code
```bash
npm install -g @anthropic-ai/claude-code
claude --version          # expect ~2.1.x
```
If global install hits permission errors (no sudo on HPC), point npm at a writable prefix:
```bash
npm config set prefix /scratch/$USER/.npm-global
export PATH=/scratch/$USER/.npm-global/bin:$PATH   # add to ~/.bashrc
npm install -g @anthropic-ai/claude-code
```

### 4. Restore the project memory (so cluster-side Claude has full context)
The 17 memory files in `hpc/claude_memory/` are a snapshot of this project's Claude
memory (goals, the whole SnapWave/wavemaker/validation history, the roadmap). Claude
keys memory by the working-dir path, so after the first `claude` launch in the repo:
```bash
cd /scratch/$USER/nj_sandy_sfincs            # wherever you cloned it
claude    # launch once so it creates ~/.claude/projects/<this-path>/memory/, then exit
# find the dir it made (path = cwd with / -> -):
MEMDIR=$(ls -d ~/.claude/projects/*nj-sandy-sfincs*/memory 2>/dev/null | head -1)
mkdir -p "$MEMDIR" && cp hpc/claude_memory/*.md "$MEMDIR"/
echo "restored memory into $MEMDIR"
```
Then cluster-side Claude starts with the same context this session has — including the
[[project-wavemaker-run]] verdict and [[project-validation-roadmap]].

### 5. Authenticate (the one fiddly headless step)
Run `claude` in the repo dir; it starts the login flow. On a headless login node:
- **Subscription (reuse your current plan):** choose the login option; Claude prints a
  **URL** — open it on your laptop browser, approve, paste the code back in the terminal.
  (This is the same plan you're on now; no extra cost beyond your subscription.)
- **API-key fallback** (if the URL flow won't round-trip): `export ANTHROPIC_API_KEY=sk-...`
  before launching. Bills the API console, not your Claude plan — only if needed.

Once `claude` launches and authenticates on Amarel, **Phase 2 starts there.**

---

## Phase 2 — preview (do this WITH cluster-side Claude, not now)
1. Clone this repo to `/scratch/$USER` (351 MB code; outputs regenerate).
2. `conda env create -f hpc/environment.yml` then editable-install hydromt_sfincs at
   commit **d8514d6** (see `environment.yml` header).
3. **Data (29 GB, ~all `data/elevation/`):** either `rsync` from the laptop, or
   re-pull on-cluster with `scripts/download_*.py`. rsync the elevation tiles;
   re-download the small forcing/validation sets.
4. **SFINCS container:** `singularity pull docker://deltares/sfincs-cpu:latest` on the
   login node → `.sif`. Swap the notebook's `docker run` cell for a `singularity exec`
   (or a Slurm-invoked) call.
5. **Slurm batch script** for the build+run (request ~16–24 GB RAM, the Phase-1 step;
   the SFINCS solve itself was 24 threads / ~13 min locally).
6. Validate it **reproduces today's run** (wavemaker: MOTF 0.53, estuary box 0.40)
   before trusting it for X2.

---

## Reference: env to reproduce (captured 2026-06-12, local WSL2)
- python 3.14.4 · hydromt 1.3.1 · hydromt_sfincs **2.0.0rc2 (editable, Deltares/hydromt_sfincs @ d8514d6, branch main)**
- xugrid 0.15.2 · xarray 2026.4.0 · numpy 2.4.5 · geopandas 1.1.3 · rasterio 1.5.0 · rioxarray 0.22.0
- SFINCS image: `deltares/sfincs-cpu:latest` (also have v2.1.1, v2.2.0 tags)
- Data footprint: **29 GB total, 29 GB in `data/elevation/`**; everything else < 80 MB. Model outputs (`model_quadtree/`, 1.1 GB) regenerate — don't transfer.
