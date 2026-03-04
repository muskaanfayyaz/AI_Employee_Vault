"""Executor skill — run plan steps and move item through vault (T023)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.skills.base import BaseSkill, SkillInput, SkillOutput
from src.models.task_item import TaskItem
from src.models.plan import Plan
from src.engine import state_machine

logger = logging.getLogger(__name__)


class ExecutorSkill(BaseSkill):
    """Execute plan steps sequentially and advance item through vault."""

    @property
    def name(self) -> str:
        return "executor"

    @property
    def version(self) -> str:
        return "1.0.0"

    def health_check(self) -> bool:
        return True

    def execute(self, skill_input: SkillInput) -> SkillOutput:
        item_path = skill_input.item_path
        dry_run = skill_input.dry_run
        vault_root = skill_input.vault_root

        if item_path is None:
            return SkillOutput(success=False, result="No item path", error="item_path required")

        try:
            item = TaskItem.from_file(item_path)
        except Exception as exc:
            return SkillOutput(success=False, result="Failed to parse item", error=str(exc))

        # Find associated plan.
        plans_dir = vault_root / "Plans"
        plan_path = plans_dir / f"PLAN_{item_path.stem}.md"
        if not plan_path.exists():
            return SkillOutput(
                success=False,
                result=f"No plan found: {plan_path.name}",
                error="Plan not found — run planner first",
            )

        try:
            plan = Plan.from_file(plan_path)
        except Exception as exc:
            return SkillOutput(success=False, result="Failed to parse plan", error=str(exc))

        actions: list[str] = []

        # Move item to In_Progress.
        in_progress_dir = vault_root / "In_Progress"
        in_progress_dir.mkdir(parents=True, exist_ok=True)

        if not dry_run:
            try:
                new_path = state_machine.move(item_path, "Needs_Action", "In_Progress", dry_run=False)
                item_path = new_path
                item.update_frontmatter(status="in_progress")
                item.to_file(item_path)
                actions.append(f"moved {item_path.name} → In_Progress/")
            except Exception as exc:
                logger.warning("Could not move to In_Progress: %s", exc)
        else:
            actions.append(f"[DRY_RUN] would move {item_path.name} → In_Progress/")

        # Execute each pending step.
        for step in plan.steps:
            if not step.is_pending():
                continue

            if step.requires_approval:
                if not dry_run:
                    plan.update_step(step.number, "in_progress")
                    plan.to_file(plan_path)
                    # Move to Pending_Approval.
                    try:
                        new_item_path = state_machine.move(item_path, "In_Progress", "Pending_Approval", dry_run=False)
                        item_path = new_item_path
                        item.update_frontmatter(status="pending_approval")
                        item.to_file(item_path)
                        actions.append(f"step {step.number} requires approval → moved to Pending_Approval/")
                    except Exception as exc:
                        logger.warning("Could not move to Pending_Approval: %s", exc)
                else:
                    actions.append(f"[DRY_RUN] step {step.number} would pause for approval")
                break  # Pause execution at approval gate.

            # Silver tier: invoke EmailDrafterSkill for email/message draft steps.
            _step_lower = step.description.lower()
            if item.type in ("email", "message") and any(
                kw in _step_lower for kw in ("draft reply", "draft response")
            ):
                try:
                    from src.skills.email_drafter import EmailDrafterSkill
                    draft_si = SkillInput(item_path=item_path, vault_root=vault_root, dry_run=dry_run)
                    draft_out = EmailDrafterSkill().safe_execute(draft_si)
                    if draft_out.success:
                        actions.extend(draft_out.actions_taken)
                        logger.info("Email draft queued for approval: %s", item_path.name)
                    else:
                        logger.warning("EmailDrafterSkill: %s", draft_out.error)
                except Exception as exc:
                    logger.warning("Could not invoke EmailDrafterSkill: %s", exc)

            # Gold tier: invoke SocialPosterSkill for all platforms (LinkedIn, Twitter/X, etc.)
            if item.type in ("social", "social_post") and "draft post" in _step_lower:
                try:
                    from src.skills.social_poster import SocialPosterSkill
                    poster_si = SkillInput(item_path=item_path, vault_root=vault_root, dry_run=dry_run)
                    poster_out = SocialPosterSkill().safe_execute(poster_si)
                    if poster_out.success:
                        actions.extend(poster_out.actions_taken)
                        logger.info("Social post draft queued for approval: %s", item_path.name)
                        break  # Pause — draft sits in Pending_Approval for human review.
                    else:
                        logger.warning("SocialPosterSkill: %s", poster_out.error)
                except Exception as exc:
                    logger.warning("Could not invoke SocialPosterSkill: %s", exc)

            # Mark step done.
            if not dry_run:
                plan.update_step(step.number, "done")
                actions.append(f"step {step.number} done: {step.description}")
            else:
                actions.append(f"[DRY_RUN] would execute step {step.number}: {step.description}")

        if not dry_run:
            plan.to_file(plan_path)

        # Check if all steps are done.
        all_done = all(s.is_done() for s in plan.steps)
        if all_done and not dry_run:
            done_dir = vault_root / "Done"
            done_dir.mkdir(parents=True, exist_ok=True)
            try:
                current_folder = item_path.parent.name
                new_path = state_machine.move(item_path, current_folder, "Done", dry_run=False)
                item_path = new_path
                item.update_frontmatter(status="done")
                item.to_file(item_path)
                actions.append(f"all steps done → moved to Done/")
            except Exception as exc:
                logger.warning("Could not move to Done: %s", exc)
        elif all_done:
            actions.append("[DRY_RUN] all steps done — would move to Done/")

        return SkillOutput(
            success=True,
            result=f"Executed {sum(1 for s in plan.steps if s.is_done())} of {len(plan.steps)} steps",
            actions_taken=actions,
            metadata={"plan_path": str(plan_path), "all_done": all_done},
        )
