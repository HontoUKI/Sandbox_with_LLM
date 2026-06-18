# Sandbox with LLM

A branch-based sandbox for small LLM-powered systems and experiments.

Each branch is a separate prototype with its own goal, README, tests, and runtime assumptions.

## Repository model

- `main` is a hub/index branch.
- Feature branches are independent prototypes.
- A branch may have its own architecture, dependencies, prompt style, tests, and docs.
- Prototypes are not required to share a common runtime.

## Branches

| Branch | Prototype | Purpose | Status |
|---|---|---|---|
| [self-esteem](docs/self-esteem/self-esteem.md) | Daria | Reflective dialogue bot that summarizes user's real strengths from conversation evidence | Prototype |
| [little-agent-planner](docs/little-agent-planner/little-agent-planner.md) | Lisa | Curious idea-planning agent that evaluates rough project ideas, researches context, and packs handoff briefs | Prototype |
