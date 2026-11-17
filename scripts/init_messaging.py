#!/usr/bin/env python3
"""Create a file-based agent messaging root.

Usage:
  python init_messaging.py --root <path> [--handle <name>] [--agent-name <name>]
                           [--role internal|external] [--machine <text>]
                           [--owner-name <name>] [--owner-role <role>] [--owner-team <team>]
                           [--owner-email <email>] [--owner-telegram <id>] [--owner-preferred <channel>]

Creates <root>/README.md, <root>/identity-template.md, <root>/identities/,
and this agent's inbox <root>/<handle>/ with processed/.

owner.md: if <root>/owner.md does not exist, the owner details are required.
Missing values come from the --owner-* flags. If stdin is a terminal, the script
asks for any that are still missing. Without a terminal it stops and lists them.
Name, role and email are required. Team, Telegram and preferred channel are optional.

Identity: if --agent-name is given, writes identities/<handle>.md from the template.
The identity's owner field is the owner name from owner.md.

The script never deletes anything. It refuses to overwrite an existing identity or owner file.
"""
import argparse
import os
import re
import shutil
import socket
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(os.path.dirname(HERE), "templates")
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def atomic_write(path, text):
    """Write text under a dotfile temp name, then rename into place."""
    folder, base = os.path.split(path)
    tmp = os.path.join(folder, "." + base + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)
    os.replace(tmp, path)


def fill_identity(template_text, values):
    out = []
    for line in template_text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key = line.split(":", 1)[0].strip()
        if key in values and values[key]:
            line = f"{key}: {values[key]}"
        out.append(line)
    return "\n".join(out).strip() + "\n"


OWNER_FIELDS = [
    # (key, prompt, required)
    ("name", "Owner full name", True),
    ("role", "Owner role (job title)", True),
    ("team", "Owner team (blank if none)", False),
    ("email", "Owner email", True),
    ("telegram", "Owner Telegram home chat ID (blank if none)", False),
    ("preferred", "Owner preferred contact channel (e.g. slack, email, telegram)", False),
]


def collect_owner(values, interactive):
    """Fill missing owner values by asking the user, or fail if we cannot ask."""
    missing = [k for k, _, req in OWNER_FIELDS if req and not values.get(k)]
    if not interactive:
        if missing:
            sys.exit("owner.md needs values for: " + ", ".join(missing) +
                     ". Pass --owner-" + " --owner-".join(m for m in missing) + " or run in a terminal to be asked.")
        return values
    for key, prompt, required in OWNER_FIELDS:
        while not values.get(key):
            if not required and key in values:
                break
            try:
                answer = input(prompt + ": ").strip()
            except EOFError:
                sys.exit("no answer for owner.md field: " + key + ". Pass --owner-" + key + " instead.")
            if answer:
                values[key] = answer
            elif not required:
                values[key] = ""
                break
        if key == "email" and values.get("email") and not EMAIL_RE.match(values["email"]):
            sys.exit(f"invalid email {values['email']!r}")
    return values


def owner_text(v):
    lines = [f"name: {v['name']}", f"role: {v['role']}"]
    if v.get("team"):
        lines.append(f"team: {v['team']}")
    lines.append("contact:")
    lines.append(f"  email: {v['email']}")
    if v.get("telegram"):
        lines.append(f"  telegram home chat: {v['telegram']}")
    if v.get("preferred"):
        lines.append(f"  preferred: {v['preferred']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", required=True, help="messaging root folder (local, UNC or synced path)")
    p.add_argument("--handle", help="this agent's handle; default: lowercased hostname")
    p.add_argument("--agent-name", help="agent name from your user; also writes the identity file")
    p.add_argument("--role", choices=["internal", "external"], help="identity role")
    p.add_argument("--machine", help="machine description")
    p.add_argument("--owner-name")
    p.add_argument("--owner-role")
    p.add_argument("--owner-team")
    p.add_argument("--owner-email")
    p.add_argument("--owner-telegram")
    p.add_argument("--owner-preferred")
    a = p.parse_args(argv)

    handle = (a.handle or socket.gethostname()).lower()
    if not HANDLE_RE.match(handle):
        sys.exit(f"invalid handle {handle!r}: use lowercase letters, digits and hyphens")

    root = os.path.abspath(a.root)
    ids = os.path.join(root, "identities")
    os.makedirs(os.path.join(root, handle, "processed"), exist_ok=True)
    os.makedirs(ids, exist_ok=True)

    shutil.copyfile(os.path.join(TEMPLATES, "messaging-README.md"), os.path.join(root, "README.md"))
    shutil.copyfile(os.path.join(TEMPLATES, "identity-template.md"), os.path.join(root, "identity-template.md"))
    print(f"root ready: {root}")
    print(f"inbox ready: {os.path.join(root, handle)}")

    owner_path = os.path.join(root, "owner.md")
    owner = None
    if os.path.exists(owner_path):
        print("owner.md already exists: left unchanged")
    else:
        values = {
            "name": a.owner_name, "role": a.owner_role, "team": a.owner_team,
            "email": a.owner_email, "telegram": a.owner_telegram, "preferred": a.owner_preferred,
        }
        values = collect_owner(values, sys.stdin.isatty())
        owner = values
        atomic_write(owner_path, owner_text(values))
        print(f"owner written: {owner_path}")

    if a.agent_name:
        target = os.path.join(ids, handle + ".md")
        if os.path.exists(target):
            sys.exit(f"refusing to overwrite existing {target}")
        with open(os.path.join(TEMPLATES, "identity-template.md"), encoding="utf-8") as f:
            text = f.read()
        owner_name = owner["name"] if owner else a.owner_name
        text = fill_identity(text, {
            "handle": handle,
            "name": a.agent_name,
            "role": a.role,
            "owner": owner_name,
            "machine": a.machine,
            "registered": date.today().isoformat(),
        })
        atomic_write(target, text)
        print(f"identity written: {target}")
    else:
        print("no --agent-name given: identity file not written (ask your user for a name first)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
