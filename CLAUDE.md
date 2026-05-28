# CLAUDE.md

Read [AGENTS.md](AGENTS.md) first — project conventions, pipeline, file layout, decisions to respect, and gotchas live there.

## Claude-specific notes

- **Respond in Vietnamese** unless the user switches language.
- **Invoke skills via the `Skill` tool** before responding when one applies (brainstorming, debugging, etc.). Don't reference a skill without calling it.
- **File references = markdown links**, not backticks: `[ir_clean.py:42](src/any2md/ir_clean.py#L42)`.
- **No emojis** in code or chat unless asked.
- **No auto-generated docs.** Planning notes, progress reports, analysis summaries — don't create them unless requested. [STATE.md](STATE.md) is the one living doc that gets updated on milestones.
- **Verify on samples** before reporting work complete. The full pipeline:
  ```powershell
  py scripts/dump_ir.py
  py scripts/clean_ir.py
  py scripts/chunk_ir.py
  ```
  For UI/agent work the loop is different — say so explicitly if you can't actually run it.
- **Ask before destructive ops.** Deleting files / branches, force-push, dropping fixtures, modifying CI — confirm first.
- **`/loop` scheduling** — don't auto-offer unless this turn produced a named artifact with a concrete future date (a dated flag, an ETA, a scheduled cleanup). Otherwise skip.
