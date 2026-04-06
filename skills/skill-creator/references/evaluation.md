# Evaluation Guide

Use this guide when the skill needs more than a quick smoke test.

## 1. Build a Small Eval Set

Create 2 to 5 prompts that sound like real user requests.

Good eval sets include:

- a normal case
- an edge case
- a near miss or ambiguous case
- input files or fixtures when the real workflow depends on them

Do not use toy prompts unless the skill itself is trivial.

## 2. Pick the Right Baseline

- **New skill:** baseline against doing the task without the skill.
- **Existing skill:** baseline against the previous version or a clean snapshot.

Use the same prompt and the same inputs for candidate and baseline runs.

## 3. Preserve Validation Integrity

When using child agents or workers for testing:

- use fresh threads
- pass the prompt, artifacts, and skill path
- do not leak the expected answer, suspected bug, or preferred fix
- prefer raw artifacts over commentary

The goal is to learn whether the skill transfers, not whether a helper agent can reverse-engineer your intent.

## 4. Run Candidate and Baseline

If parallel workers exist, start candidate and baseline in the same round so conditions stay comparable. If they do not, run them sequentially and note that the comparison is weaker.

Save artifacts in a simple iteration workspace:

```text
workspace/
└── iteration-1/
    ├── eval-01-name/
    │   ├── prompt.txt
    │   ├── input-files/
    │   ├── candidate/
    │   ├── baseline/
    │   ├── grading.json
    │   └── feedback.md
    └── summary.md
```

If timing, token, or cost metrics are available, save them next to each run.

## 5. Grade What Can Be Graded

Use assertions only for checks that can be evaluated reliably:

- file created or not created
- required fields present
- structure preserved
- exact transform completed

For writing quality, design taste, or nuanced workflow judgment, use human review instead of fake precision.

## 6. Review Outputs

If a browser or review UI is available, create a lightweight comparison surface. Otherwise present the outputs inline or point the user to saved files.

Ask the reviewer to focus on:

- whether the output solved the real task
- whether the agent skipped important steps
- whether the skill forced unnecessary work
- whether repeated mistakes suggest a missing script, reference, or constraint

## 7. Iterate Correctly

After each round:

- read outputs and execution traces, not just scores
- remove instructions that are not earning their keep
- generalize from feedback instead of patching one prompt
- promote repeated work into reusable resources
- rerun the full eval set after meaningful changes

Stop when the results are consistently good, the user is satisfied, or further changes stop producing clear gains.

## 8. Tune Discovery Metadata

When discovery is metadata-driven, test it explicitly.

Create 16 to 20 realistic prompts:

- some should trigger
- some should not
- the negative cases should be near misses, not nonsense

If the host lets you test real trigger behavior, use it. Otherwise review the metadata manually against the prompt set and tighten ambiguous wording.
