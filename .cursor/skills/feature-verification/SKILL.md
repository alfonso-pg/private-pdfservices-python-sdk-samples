---
name: feature-verification
description: Runs doc-architect and pdf-verifier simultaneously when a new feature or sample is created. Use when a new sample script is added, a feature is completed, or the user says a new feature is done.
---

# Feature verification

When a **new feature or sample** is created in the repo, run **doc-architect** and **pdf-verifier** **simultaneously** (in parallel).

## When to apply

- User completes a new sample script or feature
- User says "new feature done," "sample is ready," or similar
- New Python sample added under `src/<module>/`
- User asks to verify or document a newly created feature

## How to run (simultaneously)

Launch **both** subagents in the **same message** with two `mcp_task` calls so they run in parallel:

1. **doc-architect** – Generate README and documentation for the new sample
2. **pdf-verifier** – Validate the sample (exception handling, run the script, report findings)

### Prompt for doc-architect

```
A new PDF Services SDK sample was created. Generate documentation for it:

1. Identify the new sample (path, operation it performs)
2. Create a README.md in the sample's directory with:
   - Overview
   - Prerequisites (Python version, dependencies, credentials, env vars)
   - How to Run (step-by-step commands)
   - Additional notes if needed
3. Match Adobe developer documentation tone (clear, concise, professional)
```

### Prompt for pdf-verifier

```
A new PDF Services SDK sample was created. Validate it:

1. Identify the new sample script from git status/diff or conversation context
2. Check ServiceApiException, ServiceUsageException, SdkException handling (per .cursor/rules/adobe-sample-engineering-standards.mdc)
3. Run the script against an appropriate file from src/resources/
4. Report: Passed, Failed, and any edge cases missed
```

## Execution

Call `mcp_task` **twice in the same turn**—one for each subagent—so both run concurrently:

- `mcp_task(subagent_type="doc-architect", prompt="...", description="Generate README for new sample")`
- `mcp_task(subagent_type="pdf-verifier", prompt="...", description="Validate new sample")`

## After both complete

Summarize results for the user:
- **doc-architect**: README location and what was generated
- **pdf-verifier**: Pass/fail status and any issues found
