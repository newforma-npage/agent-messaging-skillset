# Agent messaging setup

Use this guide when someone wants a file-based messaging system between their agents, or wants a new agent to join one.
The messaging root can be any folder every participating machine can reach.

## 1. Choose the messaging root

Ask the operator where the messaging folder should live. Options: a local folder, a network share (UNC path), or a synced folder. Do not guess. Every machine that joins must be able to read and write the root.

## 2. Create the root

```
python scripts/init_messaging.py --root "<ROOT>" --handle "<hostname lowercase>" --agent-name "<name from user>" --role internal --owner "<owner>" --machine "<machine description>"
```

This creates the README, the identity template, `identities\`, and this agent's inbox with `processed\`. It writes the identity file only when `--agent-name` is given. Ask the user for the name first.

## 3. Verify

- Confirm `<ROOT>\README.md`, `<ROOT>\identity-template.md`, `<ROOT>\identities\<handle>.md` and `<ROOT>\<handle>\processed\` exist.
- Read the identity file back and check every field is filled in.

## 4. Create the inbox scheduled job

Create a recurring job named `<handle> agent inbox`, every 5 minutes, local delivery. Its prompt must follow conventions 1 to 6 of the messaging README: check the inbox, reply, relay only when asked, move handled files to `processed\`, delete nothing, and never run approval-gated actions.

- **Internal agents:** give it access to a search tool over its own past session history (if the platform has one).
- **External agents:** ask the user whether to give it that history-search access, wait for the answer, and leave it out until they say yes.

Confirm the job is enabled and has a next run time before reporting success.

## 5. Introduce the agent

Send an intro file to every other agent in `identities\` (dotfile temp, then rename), with `from`, `to`, `subject: intro: ...`, `date` and a body with name, handle, purpose and identity path. Ask for a `reply: none` ack.

## Rules

- Never write into another agent's `processed\` folder.
- Never overwrite an existing identity file. Ask the user if one already exists.
- Do not build, install or run anything during setup. Setup is registration and messaging only.
- Approval-gated actions (installs, DB/service/registry/scheduled-task changes, external posts, secrets) need the operator's direct approval in the agent's own session, never a message.
