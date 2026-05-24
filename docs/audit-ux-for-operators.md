# Audit UX For Operators

AI Audit Shelf is easiest to explain to non-technical operators when it starts with the pain, not the metaphor.

The core pain is:

> I cannot explain why this AI workflow changed, failed, or improved.

This guide shows how an operator can use chapters, books, and shelves to make an AI workflow easier to review, debug, and hand over to a teammate or client.

## Before

A typical AI-assisted workflow often starts like this:

- prompts are copied between chat tools
- screenshots are stored in a folder
- output files are renamed manually
- model, prompt, and tool changes are remembered informally
- quality changes are hard to reproduce

This works for experiments, but it breaks down when the workflow becomes part of real operations.

## Problem

When an AI workflow has no audit trail, the operator cannot answer basic questions:

- What input created this output?
- Which model, prompt, tool, or human step changed?
- Was the failed run a one-off error or a workflow regression?
- Can another person reproduce the same result?
- What should be shared with a client, manager, or auditor?

The issue is not just storage. The issue is explainability.

## After

With AI Audit Shelf, each meaningful workflow step becomes a chapter. Related chapters are bundled into a book. New workflow versions become new editions.

Example workflow: support ticket triage.

```text
Shelf: Support Automation
  Book: Ticket Triage v1
    Chapter 1: Receive ticket text
    Chapter 2: Classify urgency
    Chapter 3: Draft support response
    Chapter 4: Human approval

  Book: Ticket Triage v2
    Chapter 1: Receive ticket text
    Chapter 2: Classify urgency with updated rubric
    Chapter 3: Draft support response with shorter tone
    Chapter 4: Human approval
```

Now the operator can compare v1 and v2 instead of guessing what changed.

## Debug Flow

When output quality changes, use this review path:

1. Identify the book edition that produced the unexpected output.
2. Compare it with the last known good edition.
3. Check each chapter for changed input, prompt, model, tool output, or actor.
4. Mark which step introduced the change.
5. Decide whether to keep the new behavior, revise the prompt, or roll back to the previous edition.

This turns "the AI got worse" into a concrete review:

- the input changed
- the prompt changed
- the model changed
- a tool returned different data
- the human approval step used a different rule

## What To Export

For non-technical stakeholders, an export should be short and operational. It does not need to include every internal detail.

Useful export fields:

- workflow name
- version or edition
- date range
- actor or agent name
- input summary
- output summary
- changed steps
- approval status
- known risks
- next action

Example handoff:

```text
Workflow: Support Ticket Triage
Edition: v2
Change: urgency rubric updated to separate billing issues from product bugs
Result: fewer billing tickets escalated to engineering
Risk: short customer messages may still be misclassified
Next action: review 20 low-confidence tickets before enabling auto-routing
```

## Operator Checklist

Before a workflow is treated as production-ready, check:

- the trigger is clear
- each chapter has a readable prompt and result
- the actor is recorded
- human approval points are explicit
- errors are logged instead of hidden
- exports are understandable to someone who did not build the workflow
- old editions remain available for comparison

The goal is not to make the metaphor clever. The goal is to make the workflow explainable enough that a founder, operator, or teammate can trust it.
