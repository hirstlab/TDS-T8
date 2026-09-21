# One procedure for every agentic tool

TDS-T8 is worked by Claude Code (local and cloud), Cowork (planning), and Zencoder.
Not every tool reads the same files, so:

- **`AGENTS.md` is the only conventions file.** `CLAUDE.md` contains exactly one
  line, `@AGENTS.md`, which Claude Code follows as an import. Never add a second
  line to `CLAUDE.md` — any content there is invisible to the other tools.
- **Anything an implementer must obey lives in `AGENTS.md`**, not only in a skill or
  command. Skills are conveniences; `AGENTS.md` is the contract.
- **The ticket skill exists twice, identically:** `.claude/skills/tds-ticket/` (Claude
  Code) and `.agents/skills/tds-ticket/` (tools that read `.agents/`). Edit one, copy
  it over the other in the same commit.
- **Cloud sessions clone from GitHub.** Anything they need must be committed:
  `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `docs/`, `.scratch/`, `.claude/skills/`,
  `.claude/scripts/`, `.claude/plans/`. The rest of `.claude/` stays local
  (`.gitignore` uses `.claude/*` with negations for exactly those three folders).
- **Do not create `GEMINI.md`** or any other per-tool conventions file; it silently
  forks the rules.

## Pipeline

- **Planning (Cowork / Claude Code):** `/grill-with-docs` → `/to-spec` → `/to-tickets`.
  Produces ADRs, `CONTEXT.md` entries, `.scratch/<effort>/spec.md`, and ticket files.
- **Pointer:** the `ACTIVE-PLAN` block at the bottom of `AGENTS.md` is written only by
  `.claude/scripts/set_plan.py` and holds a pointer (effort paths, next ticket), never
  a copy of a spec.
- **Implementation (any tool):** the `tds-ticket` skill, or `AGENTS.md` §12 for tools
  without skills.
