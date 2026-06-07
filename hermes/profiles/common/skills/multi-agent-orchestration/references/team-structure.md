# Team Structure Reference

## Complete Six-Agent Team

Used in Zero Factory: a complete software factory with pipeline-aware coordination.

### Agent Identities

1. **Orchestrator** (CEO)
   - Breaks goals into work packages, dispatches agents, tracks kanban, manages handoffs
   - Never writes code directly; never reviews code — delegates everything
   - Tools: hermes-cli, delegation, kanban, cronjob, file, terminal, web

2. **Researcher** (Architect)
   - Technical research, architecture design, feasibility analysis, technical specs
   - Produces detailed specs before Builder starts coding
   - Tools: web, browser, file, terminal, search_files

3. **Builder** (Engineer)
   - Feature implementation, bug fixes, refactoring, test writing, documentation
   - Backend: TypeScript (Bun/Node), Go, PostgreSQL, Redis
   - Frontend: Svelte, Astro, Tailwind CSS, Capacitor
   - Tools: file, terminal, search_files, web

4. **Reviewer** (Code Reviewer)
   - Code quality gate: correctness, performance, security, maintainability
   - Blocks only for serious issues (bugs, security, major architecture flaws)
   - Non-blocking: minor style nitpicks
   - Tools: file, terminal, search_files, web

5. **QA** (Quality Assurance)
   - Test design, integration testing, performance testing, regression testing
   - Focus on breaking what's built, not testing what works
   - Reports bugs with clear reproduction steps and severity
   - Tools: file, terminal, search_files, web

6. **Scribe** (Documentation)
   - API docs, architecture docs, changelogs, tutorials, knowledge base
   - Prioritizes accuracy over completeness, updates alongside code
   - Avoids speculation — documents what exists
   - Tools: file, terminal, search_files, web

## Pipeline Variations

### Standard Pipeline
```
Goal → Researcher → Builder → Reviewer → QA → Scribe → Done
```

### Minimal Pipeline (2-3 agents)
```
Goal → Builder → Reviewer → Done
```

### Fast Loop
```
Goal → Builder + QA (parallel) → Reviewer → Done
```

### Research-First
```
Goal → Researcher (long research) → Builder → QA → Done
```

## Cost Optimization Tips

1. Each agent gets only its relevant toolset (no social tools for coders)
2. Max turns per agent: 60-90 (short enough to prevent runaway)
3. All non-essential skills disabled by default (hundreds of skills available, only need per-role subset)
4. Enable compression (target_ratio: 0.2)
5. Enable prompt caching (5m TTL)
6. Short system prompts — no fluff, no markdown headers
