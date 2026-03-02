---
id: "0001"
title: gold-tier-spec-business-integration
stage: spec
date: 2026-02-26
surface: agent
model: claude-sonnet-4-6
feature: 002-gold-tier
branch: 002-gold-tier
user: muskaan
command: /sp.specify
labels: [spec, gold-tier, odoo, social-media, ceo-briefing, ralph-wiggum, retry, graceful-degradation]
links:
  spec: specs/002-gold-tier/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/002-gold-tier/spec.md
  - specs/002-gold-tier/checklists/requirements.md
  - history/prompts/002-gold-tier/0001-gold-tier-spec-business-integration.spec.prompt.md
tests:
  - Spec validated: zero [NEEDS CLARIFICATION] markers
  - Checklist: all 12 items passing
---

## Prompt

Extend system to Gold Tier.

Add:
- Odoo accounting integration via JSON-RPC
- LinkedIn, Facebook, Instagram, Twitter automation
- Weekly CEO briefing generator
- Subscription audit logic
- Ralph Wiggum autonomous loop
- Retry handler
- Graceful degradation

Include:
- Cross-domain integration architecture
- Security boundaries
- Approval thresholds
- Audit logging schema

## Response snapshot

Created branch `002-gold-tier` and wrote full Gold Tier specification at `specs/002-gold-tier/spec.md`.

Spec covers 6 user stories (P1–P4):
1. Odoo Business Event Detection & Response (P1)
2. Social Media Drafting & Approval (P2)
3. Weekly CEO Briefing (P3)
4. Subscription Audit (P3)
5. Ralph Wiggum Autonomous Improvement Loop (P4)
6. Retry Handler & Graceful Degradation (P2)

49 functional requirements (FR-G001–FR-G049) covering: Odoo operations (draft-only invoices, approval-gated payments), social media (4 platforms, approval-required publish), CEO briefing (9 sections with graceful fallback), subscription anomaly detection, Ralph Wiggum loop with deduplication guard, unified retry handler, graceful degradation with per-integration isolation, cross-domain orchestration, security boundaries (credential-never-in-vault rule), extended audit log schema, and approval thresholds table.

10 success criteria (SC-G001–SC-G010). All checklist items pass.

## Outcome

- ✅ Impact: Full Gold Tier specification created. Provides complete business-language requirements for Odoo integration, 4-platform social media, CEO briefing, subscription audit, Ralph Wiggum loop, retry handler, and graceful degradation. Ready for `/sp.plan`.
- 🧪 Tests: Zero [NEEDS CLARIFICATION] markers; all 12 checklist items pass
- 📁 Files: specs/002-gold-tier/spec.md, specs/002-gold-tier/checklists/requirements.md
- 🔁 Next prompts: `/sp.plan` to generate architecture and design; optionally `/sp.clarify` if refinements needed
- 🧠 Reflection: Spec deliberately keeps JSON-RPC as an assumption (not a requirement) to stay implementation-agnostic while honouring the user's stated constraint. The approval thresholds table (FR-G009) is the single most critical constraint — all planning decisions touching financial operations must be validated against it.

## Evaluation notes (flywheel)

- Failure modes observed: none — clean first pass, no clarification markers needed
- Graders run and results (PASS/FAIL): checklist/requirements.md — PASS (12/12)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Add explicit SLA targets to SC-G001 once Odoo polling interval is confirmed during planning
