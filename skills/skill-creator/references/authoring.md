# Authoring Guide

Use this guide when creating or revising the skill itself.

## 1. Understand the Job

Start by extracting information from the conversation and existing files. Ask follow-up questions only for the missing pieces.

Lock down these points before writing:

1. What should this skill enable another agent to do?
2. What kinds of user requests should trigger it?
3. What outputs or artifacts should it produce?
4. Where should the skill be installed or stored?
5. Which examples define success and failure?
6. Which host-specific metadata or packaging rules apply?

## 2. Name the Skill Well

- Use lowercase hyphen-case.
- Keep the name short and descriptive.
- Prefer names that describe the action or domain.
- Use a namespace only when it improves clarity.

## 3. Plan the Folder

At minimum, create `SKILL.md`.

Add supporting directories only when they reduce repeated work:

```text
skill-name/
├── SKILL.md
├── scripts/      # deterministic or repetitive operations
├── references/   # docs loaded only when needed
├── assets/       # templates, fixtures, starter files, media
└── host metadata # manifest or UI files, only if required
```

## 4. Decide What to Bundle

For each representative user example, ask what would otherwise be rediscovered or rewritten every time.

Bundle:

- **Scripts** when reliability or repetition matters.
- **References** for long schemas, APIs, rules, or domain knowledge.
- **Assets** for templates, scaffolds, fixtures, icons, or starter projects.

If multiple test runs independently produce the same helper script or boilerplate, promote that pattern into the skill.

## 5. Write `SKILL.md`

Use imperative instructions aimed at another agent.

### Discovery metadata

- Include every required field for the host platform.
- Put "when to use this skill" information in the discovery metadata when possible.
- At minimum, provide a clear `name` and `description`.
- Add optional metadata only when the platform actually consumes it.

### Body

- Explain what to do and why it matters.
- Keep the main file focused on workflow, branching, and decision points.
- Move bulky examples and variants into `references/`.
- Link directly to references from `SKILL.md`; avoid deep chains.
- Prefer short, realistic examples over long tutorials.

## 6. Keep Context Lean

The main skill body competes with the rest of the task for attention. Cut anything that does not materially improve execution:

- repeated explanations
- generic background the model likely knows
- giant reference dumps in the main file
- examples that do not clarify a real edge case

## 7. Match Specificity to Fragility

- Use low-freedom instructions or scripts for brittle sequences.
- Use medium-freedom patterns when there is a preferred shape with some variation.
- Use high-level guidance when multiple valid approaches exist.

Do not overconstrain flexible work just because one example happened to work.

## 8. Keep Metadata in Sync

If the host platform uses an extra manifest, UI file, or packaging file:

- regenerate or update it after substantial edits
- keep its discovery text aligned with `SKILL.md`
- delete stale placeholder fields instead of leaving misleading values around

## 9. What Not to Add

Unless the platform requires them, do not create:

- `README.md`
- `CHANGELOG.md`
- installation notes
- dev diaries
- process notes

The skill should contain what another agent needs to execute the work, not a history of how it was created.
