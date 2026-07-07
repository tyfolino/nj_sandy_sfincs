#!/usr/bin/env bash
# hpc/vscode_node.sh — grab a main-redhat compute node and HOLD it (tmux + salloc)
# so you can attach desktop VSCode (Remote-SSH) to it and run the notebook + Claude
# Code on the node — never on the login node.
#
# After the node is ready, the sfincs env tarball (sfincs-env.tar.gz) is unpacked
# to /tmp/$USER/sfincs on the compute node so Python imports hit local disk instead
# of GPFS — pandas goes from ~16s → ~1s. A "Python (sfincs-local)" Jupyter kernel
# is registered pointing at that local env.
#
# ONE-TIME SETUP before first use:
#   ./hpc/pack-env.sh          # ~3 min; redo after any micromamba install into sfincs
#
# USAGE (run on an Amarel login node, from the repo root or anywhere):
#   ./hpc/vscode_node.sh                       # allocate w/ defaults, print connect info
#   ./hpc/vscode_node.sh -m 250G -t 12:00:00   # override memory / walltime
#   ./hpc/vscode_node.sh --status              # show the node you're holding (if any)
#   ./hpc/vscode_node.sh --stop                # release the allocation
#
# Defaults: -p main-redhat -c 32 --mem 128G -t 08:00:00
#   main-redhat node tiers: 192 GB / 256 GB / 512 GB (max single-node ~500G).
#
# ─────────────────────────────────────────────────────────────────────────────
# ONE-TIME laptop setup — put this in your laptop's ~/.ssh/config (replace <netid>):
#
#   Host amarel
#     HostName amarel-new.hpc.rutgers.edu
#     User tpj8
#
#   # Option A (simple): paste the node this script prints into HostName each session
#   Host amarel-job
#     HostName halXXXX
#     User <netid>
#     ProxyJump amarel
#
#   # Option B (zero edits ever): auto-resolve to whatever node your job is on
#   Host amarel-job
#     User <netid>
#     ProxyCommand ssh amarel "nc \$(squeue -u <netid> -h -t R -o %N | head -1) 22"
#
# Then in VSCode:  Remote-SSH → Connect to Host → amarel-job
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PART="${VSCODE_PART:-main-redhat}"
CORES="${VSCODE_CORES:-32}"
MEM="${VSCODE_MEM:-128G}"
TIME="${VSCODE_TIME:-08:00:00}"
JOB="vscode"
SESS="vscode"
ACTION="start"

usage(){ sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p)            PART="$2";  shift 2;;
    -c)            CORES="$2"; shift 2;;
    -m|--mem)      MEM="$2";   shift 2;;
    -t)            TIME="$2";  shift 2;;
    --status)      ACTION="status"; shift;;
    --stop)        ACTION="stop";   shift;;
    -h|--help)     usage;;
    *) echo "unknown arg: $1"; usage;;
  esac
done

current_node(){
  local nl
  nl=$(squeue -u "$USER" -n "$JOB" -h -t R -o "%N" 2>/dev/null | head -1)
  [[ -n "$nl" ]] && scontrol show hostnames "$nl" 2>/dev/null | head -1
}

if [[ "$ACTION" == "stop" ]]; then
  scancel -u "$USER" -n "$JOB" 2>/dev/null
  tmux kill-session -t "$SESS" 2>/dev/null
  echo "released the '$JOB' allocation."
  exit 0
fi

node="$(current_node)"

if [[ "$ACTION" == "status" ]]; then
  [[ -n "$node" ]] && echo "holding compute node: $node" || echo "no '$JOB' allocation running."
  exit 0
fi

if [[ -z "$node" ]]; then
  command -v tmux >/dev/null || { echo "ERROR: tmux not found on this login node — install it or use 'screen'."; exit 1; }
  tmux has-session -t "$SESS" 2>/dev/null && tmux kill-session -t "$SESS"
  echo "Allocating: -p $PART -c $CORES --mem $MEM -t $TIME  (held in tmux session '$SESS')..."
  tmux new-session -d -s "$SESS" \
    "salloc -p '$PART' -J '$JOB' -c '$CORES' --mem='$MEM' -t '$TIME' sleep infinity"
  for _ in $(seq 1 90); do
    node="$(current_node)"; [[ -n "$node" ]] && break; sleep 2
  done
fi

if [[ -z "$node" ]]; then
  echo "Still pending in the queue. Check again with:  $0 --status   (or: squeue -u $USER -n $JOB)"
  exit 0
fi

# ── Deploy sfincs env to compute node local /tmp ──────────────────────────────
TARBALL="$PROJ/sfincs-env.tar.gz"
LOCAL_ENV="/tmp/$USER/sfincs"

if [[ ! -f "$TARBALL" ]]; then
  echo "WARNING: $TARBALL not found — skipping local env deploy."
  echo "         Run ./hpc/pack-env.sh once to enable fast imports."
else
  echo "Deploying sfincs env to $node:$LOCAL_ENV ..."
  ssh -o StrictHostKeyChecking=no "$node" bash <<ENDSSH
    set -euo pipefail
    if [[ -d "$LOCAL_ENV" ]]; then
      echo "  local env already present, skipping unpack."
    else
      mkdir -p "$LOCAL_ENV"
      echo "  unpacking $(du -sh "$TARBALL" | cut -f1) tarball..."
      tar -xzf "$TARBALL" -C "$LOCAL_ENV"
      # Fix hardcoded paths left by conda-pack
      "$LOCAL_ENV/bin/conda-unpack"
      # Wire in the editable hydromt_sfincs (skipped by conda-pack) via a .pth file
      SITELIB=\$("$LOCAL_ENV/bin/python" -c "import sysconfig; print(sysconfig.get_path('purelib'))")
      echo "$PROJ/hydromt_sfincs" > "\$SITELIB/hydromt_sfincs_editable.pth"
      echo "  registering Jupyter kernel..."
      "$LOCAL_ENV/bin/python" -m ipykernel install --user \
        --name sfincs-local --display-name "Python (sfincs-local)"
      echo "  done."
    fi
ENDSSH
  echo "Env ready on $node."
fi
# ─────────────────────────────────────────────────────────────────────────────

cat <<EOF

  ✔ compute node ready:  $node
    ($CORES cores · $MEM · walltime $TIME · partition $PART)

  → Desktop VSCode:  Remote-SSH: Connect to Host…  →  amarel-job
    (Option-A ssh config: set  HostName $node  first; Option-B resolves it automatically.)

  In VSCode, select the "Python (sfincs-local)" kernel — it runs from local /tmp
  on the compute node so imports are fast (no GPFS metadata overhead).

  The GPFS-backed "Python (sfincs)" kernel still works if you need it, but will
  be slow. Re-run this script if you switch to a new compute node mid-session.

  Heavy SFINCS solves still go to a batch job:  sbatch hpc/sfincs_run.slurm <model_dir>
  When finished, free the node:  $0 --stop
EOF
