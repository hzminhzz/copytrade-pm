# Operator runbook

The supported operational procedure is [Appliance operations](AGENT-NATIVE-OPERATIONS.md). Start with `copytrade-pm appliance status --json`, then use the relevant native CLI leaf.

| Question | Owner |
| --- | --- |
| What is running, stale, blocked or drifted? | `appliance status` |
| Apply validated configuration to native systemd units | `appliance reconcile` |
| Recover source, quotes and paper from durable journals | `appliance recover` |
| Activate an exact-SHA verified mainline candidate | `appliance update` |
| Adopt pinned historical observation membership | `appliance adopt` |
| Inspect/migrate point-in-time facts | `facts` |
| Reconcile researched seats and stage releases | `roster`, `paper`, `release` |

Mutation commands default to dry run; inspect their `--help`. Preserve original evidence and independent owner journals. A software recovery restores code, not old financial state. Prop-Production accounts and their execution permission remain outside appliance lifecycle.

Earlier versions of this runbook are retained in Git. They describe retired experiment engines and deployment systems and are not active operating instructions.
