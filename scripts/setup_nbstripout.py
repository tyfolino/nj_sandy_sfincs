#!/usr/bin/env python
"""
Set up the nbstripout git clean filter for this repo, so notebooks are stripped
of outputs + volatile metadata automatically on every `git add`/commit.

Run ONCE per clone (the git filter config lives in .git/config, which is NOT
committed — only `.gitattributes`, the trigger, travels with the repo):

    <env-python> scripts/setup_nbstripout.py        # e.g. ~/miniforge3/envs/sfincs/bin/python

It uses the interpreter that runs it (`sys.executable`) for the filter command,
so it picks up the right env on each machine (local miniforge vs Amarel micromamba).

What the filter strips (and, deliberately, what it does NOT):
  - clears all cell outputs + execution_count           (the bloat / main git churn)
  - drops metadata.kernelspec + metadata.language_info  (kernel-agnostic; no version churn
                                                          across the laptop vs Amarel envs)
  - KEEPS cell ids (--keep-id) — without this nbstripout renumbers cells 0,1,2…,
    which would break the stable `0137685c`-style ids that the project memory keys off.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
EXTRA_KEYS = "metadata.kernelspec metadata.language_info"
CLEAN = f'"{PY}" -m nbstripout --keep-id --extra-keys "{EXTRA_KEYS}"'
TEXTCONV = f'"{PY}" -m nbstripout -t --keep-id --extra-keys "{EXTRA_KEYS}"'


def git(*args):
    subprocess.run(["git", "-C", str(REPO), *args], check=True)


def main():
    # nbstripout must be importable in this interpreter
    subprocess.run([PY, "-m", "nbstripout", "--version"], check=True)

    # --install writes the *.ipynb trigger to the committed .gitattributes and sets
    # smudge=cat / required=true. We then override clean + textconv to bake in the
    # flags (--install does not accept --keep-id/--extra-keys).
    git_install = [PY, "-m", "nbstripout", "--install", "--attributes", ".gitattributes"]
    subprocess.run(git_install, cwd=str(REPO), check=True)

    git("config", "filter.nbstripout.clean", CLEAN)
    git("config", "diff.ipynb.textconv", TEXTCONV)

    print("\nnbstripout filter configured for this clone:")
    print(f"  clean filter: {CLEAN}")
    print("  (.gitattributes is committed; this filter config is local to this clone)")


if __name__ == "__main__":
    main()
