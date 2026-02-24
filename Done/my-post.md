---
id: test-li-post-001
type: social
source: manual
priority: high
status: done
requires_approval: false
classification: local_only
created_at: 2026-02-25T00:00:00+00:00
updated_at: 2026-02-24T19:40:36.087949+00:00
tags: [linkedin, ai, automation]
---

# Building an AI Employee That Manages My Inbox

## Content

I've been building a local-first AI Employee system that runs entirely on my machine — no cloud dependencies, no subscription fees.

It watches my Gmail, drafts email replies using Gemini AI, and now posts to LinkedIn automatically — all with a human-approval step before anything is sent.

The stack is simple: Python, watchdog, Obsidian vault folders as a state machine, and a few Google APIs.

Every outbound action — email, LinkedIn post — goes through a Pending_Approval folder first. Nothing is sent without my review.

What started as an experiment is turning into a real productivity layer. The goal: spend less time on repetitive communication, more time on actual work.

Happy to share more about the architecture if anyone is curious.

## Next Steps

- [ ] Review post content
- [ ] Draft LinkedIn post (AI)
- [ ] Route to Pending_Approval