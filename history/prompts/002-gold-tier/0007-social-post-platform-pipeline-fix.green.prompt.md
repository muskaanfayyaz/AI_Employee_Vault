---
id: "0007"
title: Social Post Platform Pipeline Fix
stage: green
date: 2026-03-03
surface: agent
model: claude-sonnet-4-6
feature: 002-gold-tier
branch: 002-gold-tier
user: muskaanfayyaz
command: fix social_post pipeline (continued from context-compacted session)
labels: ["bugfix", "social_poster", "filesystem_watcher", "platform_resolution"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/skills/social_poster.py
  - src/watchers/filesystem.py
tests:
  - manual: drop twitter-ai-employee-24-7.md → Needs_Action → Pending_Approval
---

## Prompt

(Continued from previous context-compacted session)

SocialPosterSkill was failing with:
"Add a '## Platform' section (e.g. 'twitter') to the item, or enable a platform in Config/<platform>_watcher.yaml."

The file `twitter-ai-employee-24-7.md` uses `platforms: [twitter]` in YAML frontmatter but has no `## Platform` markdown section.

Additionally, the filesystem watcher was wrapping vault items (files with proper TaskItem frontmatter) in a generic `-metadata.md` wrapper with `type: file`, losing the original `type: social_post` and `platforms: [twitter]` fields.

## Response snapshot

**Bug 1 fixed — `SocialPosterSkill` platform resolution** (`src/skills/social_poster.py`):
- Added `_extract_frontmatter_platforms(text)` helper that parses `platforms: [twitter]` from YAML frontmatter
- Platform resolution priority (in `execute()`): `## Platform` section → YAML `platforms:` field → config/explicit override

**Bug 2 fixed — Filesystem watcher vault item detection** (`src/watchers/filesystem.py`):
- Added `_VAULT_ITEM_TYPES` set of non-generic item types
- Added `_is_vault_item(path)`: checks if a file has a recognised non-generic `type` in frontmatter
- Added `_ensure_needs_action_status(path)`: sets `status: needs_action` via regex in frontmatter
- `create_action_file()` now detects vault items and returns `dest_file` directly, skipping the `-metadata.md` wrapper
- Added `import re` to imports

## Outcome

- ✅ Impact: Files dropped into drop_folder/ with type: social_post now flow through the pipeline with correct type and platform, creating Twitter drafts in Pending_Approval/
- 🧪 Tests: Manual — delete stale Needs_Action/*-metadata.md, restart system, startup scan re-queues drop_folder/twitter-ai-employee-24-7.md
- 📁 Files: src/skills/social_poster.py, src/watchers/filesystem.py
- 🔁 Next prompts: Approve Twitter draft in Pending_Approval/, Odoo watcher disable unused modules
- 🧠 Reflection: Two layered bugs: (1) platform field not read from frontmatter, (2) filesystem watcher discarding type info by wrapping in generic metadata file. Both needed to be fixed for end-to-end social post flow.

## Evaluation notes (flywheel)

- Failure modes observed: SocialPosterSkill error message misleading (said "add ## Platform section" but real issue was upstream metadata wrapping losing the type)
- Graders run and results (PASS/FAIL): none automated
- Prompt variant (if applicable): null
- Next experiment: add unit test for _extract_frontmatter_platforms and _is_vault_item helpers
