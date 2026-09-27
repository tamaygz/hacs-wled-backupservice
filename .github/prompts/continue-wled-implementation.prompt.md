---
name: "Continue WLED Implementation"
description: "Continue the planned implementation of the WLED Backup Service using the roadmap and the coordinator agent."
agent: "WLED Implementation Coordinator"
model: ['GPT-5.4 (copilot)', 'GPT-5 (copilot)']
argument-hint: "Optional: plan number, constraint, blocker, or focus area"
---
Continue implementing this repository using the roadmap.

Start with [the master index](../../docs/prompts/plans/0_index.md), then select the first
incomplete plan whose dependencies are complete unless I explicitly override that in my
arguments.

Requirements for this run:

- Maintain a todo list for the active slice.
- Update the relevant plan file and [the master index](../../docs/prompts/plans/0_index.md)
  when progress, blockers, or architectural discoveries occur.
- Coordinate subagents where useful for focused exploration or QA.
- Prefer cheap delegated read/search/web work via the low-cost worker before spending a
  more expensive reasoning pass.
- Keep the repository in a working state.
- Do not take shortcuts or silently expand scope into later plans.
- If a user decision, blocker, or risky assumption appears, stop at a clean checkpoint,
  summarize it clearly, and wait for the next iteration.

Model preference for this workflow:

- use cheap models where capable for lightweight exploration and summarization
- use GPT-5.4 for higher-complexity implementation and coordination
- do not use Sonnet or Opus

If I supplied arguments with this prompt, treat them as additional constraints or focus for
this iteration.