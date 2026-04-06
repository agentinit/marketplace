# Templates

Adapt these to the host platform instead of copying them blindly.

## Minimal Frontmatter

```yaml
---
name: my-skill
description: What the skill does and when it should trigger.
---
```

## AgentInit Marketplace Frontmatter

```yaml
---
name: my-skill
description: What the skill does and when it should trigger.
keywords: [keyword1, keyword2]
user_invocable: true
---
```

## Eval Manifest

```json
{
  "skill_name": "my-skill",
  "evals": [
    {
      "id": "eval-01",
      "name": "basic-case",
      "prompt": "A realistic user request",
      "files": [],
      "expected_outcome": "Short statement of success",
      "assertions": []
    }
  ]
}
```

## Per-Eval Metadata

```json
{
  "eval_id": "eval-01",
  "eval_name": "basic-case",
  "prompt": "A realistic user request",
  "assertions": [
    {
      "text": "The output contains the required heading",
      "type": "objective"
    }
  ],
  "notes": ""
}
```

## Grading Result

```json
{
  "run_id": "eval-01-candidate",
  "result": "pass",
  "expectations": [
    {
      "text": "The output contains the required heading",
      "passed": true,
      "evidence": "Heading found in line 1"
    }
  ],
  "summary": "Passed all objective checks."
}
```

## Review Checklist

```markdown
# Review Checklist

- Did the output solve the actual user request?
- Did the agent skip an important step?
- Did the skill force unnecessary work?
- What should change before the next iteration?
```

## Discovery Prompt Set

```json
[
  {
    "query": "Can you turn this repeated release-note cleanup workflow into a reusable skill for our team?",
    "should_trigger": true
  },
  {
    "query": "Explain what a software skill matrix is for a team retrospective.",
    "should_trigger": false
  }
]
```
