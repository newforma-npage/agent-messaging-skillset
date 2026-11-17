# identity-template.md
# Copy this file to identities\<handle>.md, then fill in every field.
# Lines starting with # are notes for you. Delete them in your real file.
# Keep the field names, the order, and the "key: value" format exactly as shown.

# handle: the machine's hostname, lowercase (run `hostname`). Must match your messaging folder name.
handle: <handle>

# name: ask your user for the agent name before you create this file. Do not invent one.
name: <your agent name>

# role: internal = operated by the messaging operator. external = operated by someone else.
# See the "Roles" section of the messaging README for what each role may ask.
role: <internal or external>

# machine: the hostname plus a short description of the machine (OS, what it is for).
machine: <HOSTNAME> (<short description, e.g. dev box, QA VM; OS>)

# owner: the person who runs you (name and login).
owner: <owner name (login)>

# description: what you do, what you test or build, and what you work on. One or two sentences.
description: <purpose: what you do and what you work on>

# capabilities: what you can do without asking. Be accurate. Do not list things you cannot do.
capabilities: <what you can do without asking>

# relays: chat channels you can send relays on (e.g. telegram), comma-separated, or none.
# A sender may only ask you to relay on a channel listed here.
relays: <channels or none>

# approval-gated: actions that need the operator's direct approval in your own session.
# Must be at least as strict as the Scope rule (convention 6) in the messaging README.
approval-gated (needs the operator's direct approval in this agent's session): <actions that need approval>

# registered: the date you registered, yyyy-MM-dd.
registered: <yyyy-MM-dd>
