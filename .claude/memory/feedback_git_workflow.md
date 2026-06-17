---
name: feedback-git-workflow
description: "Git workflow preference: Claude may stage (git add) freely, but the user does the commit and push themselves."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 08346867-a115-4cc6-ba9e-64fedfeb2b3a
---

The user handles `git commit` and `git push` themselves; do NOT run them. Staging
(`git add`) is welcome — stage the relevant changed/new files and leave the tree
ready, then stop and let the user commit/push.

**Why:** The user wants final control over what lands in history and goes to the
remote (`tyfolino/nj_sandy_sfincs`), especially since commits can include personal
working notes (e.g. the [[project-wavemaker-run]] memory snapshot in `hpc/claude_memory/`).

**How to apply:** When work is ready to record, `git add` the relevant paths, show
`git status --short`, optionally suggest a commit message, then stop. Don't commit or
push unless explicitly asked.
