# Documentation

| Doc | What it is | Read when |
|---|---|---|
| **[SYSTEM.md](SYSTEM.md)** | **As-built reference** — what exists and runs today | You want to understand or change the current system |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Generic chat-engine design, project-agnostic | You want to reuse this pattern on another project |
| [BUILD_PLAN.md](BUILD_PLAN.md) | Build plan, novice implementation guide, TDD method | You are building something like this from scratch |

Test evidence lives in [`../test_results/`](../test_results/) — one file per
layer plus [SUMMARY.md](../test_results/SUMMARY.md).

## Quick orientation

- **Change the agent's behavior** → `prompts.py` (single control point)
- **Change the menu** → `menu/menu_flat.json`
- **Change tuning** → `config.py` / `.env`
- **See what the model receives** → `DEBUG_CONTEXT=true`, or `/context` in the CLI
- **Add a storage backend** → implement `storage/base.py`
- **Add an LLM provider** → implement `providers/base.py`
