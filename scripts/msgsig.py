#!/usr/bin/env python3
"""Sign and verify messages with OpenSSH signatures (ssh-keygen -Y).

Usage:
  python msgsig.py sign   <message.md> --key <private key path>
      Writes <message.md>.sig next to the message.

  python msgsig.py verify <message.md> --identities <identities folder>
      Reads the 'from:' header, takes the 'pubkey:' line from identities/<handle>.md,
      and checks <message.md>.sig. Exit 0 = valid. Anything else = do not act on it.

Needs ssh-keygen on PATH (ships with Windows 10+ and OpenSSH).
The signature covers the whole message file, so do not edit a message after signing it.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

NAMESPACE = "messaging"
FROM_RE = re.compile(r"^from:\s*(\S+)\s*$", re.MULTILINE)
PUBKEY_RE = re.compile(r"^pubkey:\s*(ssh-ed25519\s+\S+)", re.MULTILINE)


def sign(message, key):
    if not os.path.isfile(key):
        sys.exit(f"no such private key: {key}")
    r = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", NAMESPACE, message],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("sign failed: " + r.stderr.strip())
    print(f"signed: {message}.sig")
    return 0


def verify(message, identities):
    with open(message, encoding="utf-8", errors="replace") as f:
        text = f.read()
    m = FROM_RE.search(text)
    if not m:
        print("REJECT: no from: header")
        return 2
    handle = m.group(1)
    ident = os.path.join(identities, handle + ".md")
    if not os.path.isfile(ident):
        print(f"REJECT: no identity file for {handle}")
        return 2
    with open(ident, encoding="utf-8", errors="replace") as f:
        pm = PUBKEY_RE.search(f.read())
    if not pm:
        print(f"REJECT: {handle} has no pubkey in its identity file")
        return 2
    sig = message + ".sig"
    if not os.path.isfile(sig):
        print(f"REJECT: no signature file {sig}")
        return 2
    with tempfile.TemporaryDirectory() as d:
        allowed = os.path.join(d, "allowed_signers")
        with open(allowed, "w", encoding="utf-8") as f:
            f.write(f'{handle} namespaces="{NAMESPACE}" {pm.group(1)}\n')
        with open(message, "rb") as data:
            r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", allowed, "-I", handle,
                                "-n", NAMESPACE, "-s", sig], stdin=data,
                               capture_output=True, text=True)
    if r.returncode != 0:
        print(f"REJECT: signature does not match {handle}'s pubkey")
        return 2
    print(f"OK: signed by {handle}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sign")
    s.add_argument("message")
    s.add_argument("--key", required=True)
    v = sub.add_parser("verify")
    v.add_argument("message")
    v.add_argument("--identities", required=True)
    a = p.parse_args(argv)
    if a.cmd == "sign":
        return sign(a.message, a.key)
    return verify(a.message, a.identities)


if __name__ == "__main__":
    sys.exit(main())
