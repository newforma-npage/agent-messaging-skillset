#!/usr/bin/env python3
"""Create a file-based agent messaging root.

Usage:
  python init_messaging.py --root <path> [--handle <name>] [--agent-name <name>]
                           [--role internal|external] [--owner <owner>] [--machine <text>]

Creates <root>\\README.md, <root>\\identity-template.md, <root>\\identities\\,
and this agent's inbox <root>\\<handle>\\ with processed\\. The handle defaults to the
lowercased hostname. If --agent-name is given, also writes identities\\<handle>.md
from the template with the supplied fields (other fields stay as placeholders).
The script never deletes anything. It refuses to overwrite an existing identity file.
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", required=True, help="messaging root folder (local, UNC or synced path)")
    p.add_argument("--handle", help="this agent's handle; default: lowercased hostname")
    p.add_argument("--agent-name", help="agent name from your user; also writes the identity file")
    p.add_argument("--role", choices=["internal", "external"], help="identity role")
    p.add_argument("--owner", help="owner name and login")
    p.add_argument("--machine", help="machine description")
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

    if a.agent_name:
        target = os.path.join(ids, handle + ".md")
        if os.path.exists(target):
            sys.exit(f"refusing to overwrite existing {target}")
        with open(os.path.join(TEMPLATES, "identity-template.md"), encoding="utf-8") as f:
            text = f.read()
        text = fill_identity(text, {
            "handle": handle,
            "name": a.agent_name,
            "role": a.role,
            "owner": a.owner,
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
