---
name: skill-creator
description: Design, refine, validate, and package reusable skills for any coding agent. Use when the user wants to convert a repeated workflow into a skill, rewrite or de-bloat an existing skill, add reusable scripts/references/assets, run baseline comparisons, improve trigger metadata, or prepare a skill for team or marketplace distribution.
keywords: ["skill creator", "create skill", "improve skill", "skill authoring", "evaluate skill", "trigger tuning", marketplace]
user_invocable: true
---

# Skill Creator

Create portable skills that are easy to trigger, cheap to load, and proven on realistic tasks.

## Default Stance

- Read the current conversation and any existing skill before you ask questions.
- Do not assume one agent, one UI, or one toolchain. Work from capabilities.
- Keep `SKILL.md` focused on workflow and decisions. Move bulky detail into `references/`.
- Prefer reusable resources over repeated explanation.
- Validate on real prompts before calling the skill complete.

## Capability Check

Decide these early and adapt the workflow to match:

1. Are child agents or parallel workers available?
2. Is there a browser or some other review surface?
3. Is there a validator, linter, or packaging command for this host?
4. Can you measure timing, tokens, or cost?
5. Does the host rely on frontmatter, a manifest, or both for discovery?

If a capability is missing, use the simpler fallback instead of forcing a platform-specific ritual.

## Workflow

1. Define the job, trigger conditions, success criteria, and install location.
2. Identify reusable scripts, references, assets, and any required host metadata.
3. Create or update the skill folder.
4. Write `SKILL.md` and only the metadata files the host actually reads.
5. Validate structure and run representative commands or scripts.
6. Run a candidate-versus-baseline eval loop when the skill is non-trivial.
7. Tune discovery metadata with realistic should-trigger and should-not-trigger prompts.
8. Clean up temporary artifacts and package the skill if it will be shared.

## Read Next

- Read `references/authoring.md` for naming, structure, writing style, and resource planning.
- Read `references/evaluation.md` for eval design, baselines, review flow, and iteration rules.
- Read `references/templates.md` when you need starter metadata, eval manifests, or review checklists.

## Non-Negotiables

- Put trigger guidance in the discovery metadata whenever the host supports it.
- Keep references one hop away from `SKILL.md`.
- Test scripts by actually running them on representative inputs.
- Do not add process junk such as `README.md` or `CHANGELOG.md` unless the host explicitly requires it.
- Do not create deceptive or unsafe skills.
