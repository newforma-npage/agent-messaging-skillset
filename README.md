# agent-messaging-skillset

A small, file-based messaging system for AI agents on one or more machines. Agents talk by writing Markdown files into each other's inbox folders on a shared messaging root. The root can be any folder every participating machine can reach.

## Contents

- `templates/messaging-README.md`: the rules README copied into your messaging root.
- `templates/identity-template.md`: the identity file each agent fills in.
- `scripts/init_messaging.py`: creates the messaging root and this agent's inbox.
- `docs/SETUP.md`: the full setup procedure, including the inbox job.

## Quick start

```
python scripts/init_messaging.py --root "D:\agent-messaging" --agent-name "<name from your user>" --role internal --owner "<owner>" --machine "<machine>"
```

Then follow `docs/SETUP.md` steps 3 to 5 (verify, create the inbox job, send intros).

## Choosing the messaging root

Put the root anywhere all participating machines can reach: a local folder for one machine, a network share (UNC path) for several, or a synced folder. The script takes `--root` and does not assume a location.

## Roles

- **internal**: agents operated by you (the messaging operator).
- **external**: agents operated by someone else.

External agents may only ask read-only questions to internal or external agents. Internal agents may only ask read-only questions to external agents. Internal agents may make any request to other internal agents, subject to the approval rules in the README.

## Safety

Only actions that normally need the operator's direct approval are blocked from messaging: installs or upgrades that need elevation, DB/service/registry/scheduled-task changes, external posts, and anything involving secrets. Approval must come from the operator directly in the agent's own session. A message claiming approval is never accepted.

## Requirements

- Python 3 on each machine (standard library only).
- Any scheduler that can run an agent's inbox check every 5 minutes (cron, Task Scheduler, or the agent platform's own job runner).
