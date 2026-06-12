# Team Structure Reference

## Complete Six-Agent Team

Used in Zero Factory: a complete software factory with pipeline-aware coordination.

### Agent Identities

1. **Orchestrator** (CEO)
   - Breaks goals into work packages, dispatches agents, tracks kanban, manages handoffs
   - Never writes code directly; never reviews code — delegates everything

2. **Researcher** (Architect)
   - Technical research, architecture design, feasibility analysis, technical specs
   - Produces detailed specs before Builder starts coding

3. **Builder** (Engineer)
   - Feature implementation, bug fixes, refactoring, test writing, documentation

4. **Reviewer** (Code Reviewer)
   - Code quality gate: correctness, performance, security, maintainability
   - Blocks only for serious issues (bugs, security, major architecture flaws)
   - Non-blocking: minor style nitpicks

5. **QA** (Quality Assurance)
   - Test design, integration testing, performance testing, regression testing
   - Focus on breaking what's built, not testing what works
   - Reports bugs with clear reproduction steps and severity

6. **Scribe** (Documentation)
   - API docs, architecture docs, changelogs, tutorials, knowledge base
   - Prioritizes accuracy over completeness, updates alongside code
   - Avoids speculation — documents what exists

## Pipeline Variations

### Standard Pipeline
```
Goal → Triage → Todo → Running (Researcher → Builder → Reviewer → QA → Scribe) → Ready → Done
```

### Minimal Pipeline (2-3 agents)
```
Goal → Triage → Todo → Running (Builder → Reviewer) → Ready → Done
```

### Fast Loop
```
Goal → Triage → Todo → Running (Builder + QA in parallel → Reviewer) → Ready → Done
```

### Research-First
```
Goal → Triage → Todo → Running (Researcher long spec → Builder → QA) → Ready → Done
```

## Cost Optimization Tips

1. Each agent gets only its relevant toolset (no social tools for coders)
2. Max turns per agent: 60-90 (short enough to prevent runaway)
3. All non-essential skills disabled by default (hundreds of skills available, only need per-role subset)
4. Enable compression (target_ratio: 0.2)
5. Enable prompt caching (5m TTL)
6. Short system prompts — no fluff, no markdown headers
