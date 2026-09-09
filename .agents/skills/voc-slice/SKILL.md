---
name: voc-slice
description: Implement, review, validate, or hand off a small Jira VOC Nexus slice with a token budget and optional Orca workers.
---

# Small verified slices

1. Read current Git state, `HANDOFF.md`, and only the relevant indexed documentation.
2. Name one behavior and its acceptance check. Use synthetic data in all development work.
3. Delegate implementation and large edits to Luna Max or GLM 5.3 through Orca's live orchestration guide; give each worker exact file ownership, inputs, non-goals, model/effort, and completion conditions. The coordinator handles scope, review decisions, verification, and publication; tiny adjustments may be direct.
4. Prefer one implementation worker. Add one bounded reviewer only for substantive runtime/ACL/replay changes. Do not run a standing panel of models.
5. Run `python3 -m unittest discover -s tests -v`, the affected fixture CLI and `git diff --check` after writers finish. Review untracked new files as well as tracked diff.
6. Fix concrete findings in scope, rerun relevant checks once, and record counts and unrun live integrations.
7. Recover every expected worker completion, release owned terminals, and update the single root `HANDOFF.md`.

Model choices and publication authority come from `AGENTS.md` and the current request.
No automatic commit, push, PR, deployment or Jira comment based on skill completion alone.

Done means the requested local behavior is runnable, documented, and its limits are explicit.
