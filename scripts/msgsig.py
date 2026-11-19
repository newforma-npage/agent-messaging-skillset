#!/usr/bin/env python3
"""Sign and verify agent messages with OpenSSH signatures (ssh-keygen -Y), v2.

Usage:
  python msgsig.py sign <message.md> --key <private key>
      Signs a LOCAL file. Adds missing date: and msg-id: header lines first, then writes
      <message.md>.sig. Copy both files into the recipient's inbox afterwards.

  python msgsig.py verify <message.md> --me <handle> [--signers FILE] [--state DIR]
                          [--mark] [--no-replay-check] [--allow-legacy] [--max-age-hours N]
      Copies the message and its .sig to a local folder, checks the copy against the local
      allowed_signers file, and checks the header (from/to/date/msg-id, replay). Prints
        OK: signed by <handle> [(external)]
        copy: <local path>
      Act only on OK, and only on the local copy. Exit 0 = valid, anything else = reject.

Local state (default ~/.agent-messaging): allowed_signers, seen.json, verified/.
allowed_signers lines: <handle> namespaces="messaging" ssh-ed25519 <key> [comment]
Change it only on the operator's instruction; identity files on the share are information only.
Run this script from a local copy; it refuses to run from a network path.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

NAMESPACE = "messaging"
EXTERNAL_PREFIX = "external:"
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
MSGID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,99}$")
DEFAULT_STATE = os.path.join(os.path.expanduser("~"), ".agent-messaging")
FUTURE_SKEW = datetime.timedelta(minutes=10)


class Reject(Exception):
    pass


def is_remote(path):
    p = os.path.abspath(path)
    if p.replace("/", "\\").startswith("\\\\"):
        return True
    if os.name == "nt" and len(p) >= 2 and p[1] == ":":
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(p[:2] + "\\") == 4  # DRIVE_REMOTE
    return False


def ssh_keygen():
    exe = shutil.which("ssh-keygen")
    if not exe:
        raise Reject("ssh-keygen not found on PATH")
    return exe


def header_lines(text):
    out = []
    for line in text.splitlines():
        if not line.strip():
            break
        out.append(line)
    return out


def parse_header(text):
    lines = header_lines(text)
    if not lines or not lines[0].lower().startswith("from:"):
        raise Reject("from: is not the first line")
    fields = {}
    for line in lines:
        if ":" not in line:
            raise Reject("malformed header line: " + line[:60])
        k, v = line.split(":", 1)
        k = k.strip().lower()
        if k in fields:
            raise Reject("duplicate header: " + k)
        fields[k] = v.strip()
    if not HANDLE_RE.match(fields["from"]):
        raise Reject("from: is not a valid handle")
    return fields


def parse_date(value):
    try:
        d = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else None


def sign(message, key):
    if is_remote(message):
        raise Reject("sign a local file, then copy it and its .sig into the inbox")
    if not os.path.isfile(key):
        raise Reject("no such private key: " + key)
    with open(message, encoding="utf-8-sig") as f:
        text = f.read()
    fields = parse_header(text)
    if not HANDLE_RE.match(fields.get("to", "")):
        raise Reject("to: is missing or not a valid handle")
    add = []
    now = datetime.datetime.now().astimezone()
    if "date" not in fields:
        add.append("date: " + now.isoformat(timespec="seconds"))
    elif parse_date(fields["date"]) is None:
        raise Reject("date: must be ISO 8601 with an offset, e.g. 2026-11-19T12:05:00-05:00")
    if "msg-id" not in fields:
        add.append("msg-id: %s-%s-%s" % (fields["from"], now.strftime("%Y%m%d%H%M%S"), secrets.token_hex(4)))
    elif not MSGID_RE.match(fields["msg-id"]):
        raise Reject("msg-id: is not valid")
    if add:
        lines = text.splitlines()
        n = len(header_lines(text))
        lines[n:n] = add
        with open(message, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    sig = message + ".sig"
    if os.path.exists(sig):
        os.remove(sig)
    cert = key + "-cert.pub"
    signer = cert if os.path.isfile(cert) else key
    r = subprocess.run([ssh_keygen(), "-Y", "sign", "-f", signer, "-n", NAMESPACE, message],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Reject("sign failed: " + r.stderr.strip())
    print("signed: " + sig + (" (certificate)" if signer == cert else ""))


def certify(pubkey, ca, handle, days, role="internal"):
    if not HANDLE_RE.match(handle or ""):
        raise Reject("--handle is not a valid handle")
    if not pubkey.endswith(".pub") or not os.path.isfile(pubkey):
        raise Reject("no such public key: " + pubkey)
    if is_remote(ca) or not os.path.isfile(ca):
        raise Reject("CA key must be an existing local file: " + ca)
    if days < 1:
        raise Reject("--days must be at least 1")
    principal = EXTERNAL_PREFIX + handle if role == "external" else handle
    r = subprocess.run([ssh_keygen(), "-q", "-s", ca, "-I", principal, "-n", principal,
                        "-V", "+%dd" % days, "-O", "clear", pubkey])
    if r.returncode != 0:
        raise Reject("certify failed")
    print("certificate: %s-cert.pub (principal %s)" % (pubkey[:-len(".pub")], principal))


def load_seen(path):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(path, seen):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def check_copy(copy, me, signers, seen, replay_check, allow_legacy, max_age_hours):
    with open(copy, "rb") as f:
        raw = f.read()
    with open(copy + ".sig", "rb") as f:
        sig_hash = "sha256:" + hashlib.sha256(f.read()).hexdigest()
    fields = parse_header(raw.decode("utf-8-sig", errors="replace"))
    handle = fields["from"]
    role = None
    for principal, name in ((handle, "internal"), (EXTERNAL_PREFIX + handle, "external")):
        r = subprocess.run([ssh_keygen(), "-Y", "verify", "-f", signers, "-I", principal,
                            "-n", NAMESPACE, "-s", copy + ".sig"], input=raw, capture_output=True)
        if r.returncode == 0:
            role = name
            break
    if role is None:
        raise Reject("signature does not match a pinned key for " + handle)
    if fields.get("to") != me:
        raise Reject("to: is %r, not %s" % (fields.get("to"), me))
    missing = [k for k in ("date", "msg-id") if k not in fields]
    legacy = bool(missing)
    if legacy and not allow_legacy:
        raise Reject("missing header: " + ", ".join(missing))
    keys = [handle + "/" + sig_hash]
    if not legacy:
        d = parse_date(fields["date"])
        if d is None:
            raise Reject("date: is not ISO 8601 with an offset")
        now = datetime.datetime.now(datetime.timezone.utc)
        if d - now > FUTURE_SKEW:
            raise Reject("date: is in the future")
        if now - d > datetime.timedelta(hours=max_age_hours):
            raise Reject("message is older than %g h" % max_age_hours)
        if not MSGID_RE.match(fields["msg-id"]):
            raise Reject("msg-id: is not valid")
        keys.append(handle + "/" + fields["msg-id"])
    if replay_check:
        for k in keys:
            if k in seen:
                raise Reject("replay: already accepted as %s" % seen[k]["file"])
    return handle, legacy, keys, role


def verify(message, me, signers, state, mark=False, replay_check=True, allow_legacy=False, max_age_hours=24.0):
    if not HANDLE_RE.match(me or ""):
        raise Reject("--me is not a valid handle")
    if is_remote(signers) or not os.path.isfile(signers):
        raise Reject("allowed_signers must be an existing local file: " + signers)
    if not os.path.isfile(message):
        raise Reject("no such message: " + message)
    if not os.path.isfile(message + ".sig"):
        raise Reject("no signature file " + os.path.basename(message) + ".sig")
    work = os.path.join(state, "verified")
    os.makedirs(work, exist_ok=True)
    dest = tempfile.mkdtemp(prefix=datetime.datetime.now().strftime("%Y%m%d-%H%M%S-"), dir=work)
    copy = os.path.join(dest, os.path.basename(message))
    try:
        shutil.copyfile(message, copy)
        shutil.copyfile(message + ".sig", copy + ".sig")
        seen_path = os.path.join(state, "seen.json")
        seen = load_seen(seen_path)
        handle, legacy, keys, role = check_copy(copy, me, signers, seen, replay_check, allow_legacy, max_age_hours)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    if mark:
        stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        for k in keys:
            seen[k] = {"file": os.path.basename(message), "at": stamp}
        save_seen(seen_path, seen)
    print("OK: signed by %s%s%s" % (handle, " (external)" if role == "external" else "",
                                   " (legacy header)" if legacy else ""))
    print("copy: " + copy)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sign")
    s.add_argument("message")
    s.add_argument("--key", required=True)
    c = sub.add_parser("certify", help="operator only: issue a certificate for an agent's public key")
    c.add_argument("pubkey")
    c.add_argument("--ca", required=True, help="local CA private key")
    c.add_argument("--handle", required=True)
    c.add_argument("--days", type=int, default=90)
    c.add_argument("--role", choices=("internal", "external"), default="internal",
                   help="external issues principal external:<handle>; verify then prints (external)")
    v = sub.add_parser("verify")
    v.add_argument("message")
    v.add_argument("--me", required=True, help="your own handle; to: must match it")
    v.add_argument("--state", default=DEFAULT_STATE)
    v.add_argument("--signers", help="default: <state>/allowed_signers")
    v.add_argument("--mark", action="store_true", help="record the message as accepted (the inbox job)")
    v.add_argument("--no-replay-check", action="store_true", help="for relay-only watchers that never act")
    v.add_argument("--allow-legacy", action="store_true", help="accept messages without date:/msg-id: (rollout only)")
    v.add_argument("--max-age-hours", type=float, default=24.0)
    a = p.parse_args(argv)
    try:
        if is_remote(__file__):
            raise Reject("msgsig.py is running from a network path; run your local copy")
        if a.cmd == "sign":
            sign(a.message, a.key)
        elif a.cmd == "certify":
            certify(a.pubkey, a.ca, a.handle, a.days, a.role)
        else:
            verify(a.message, a.me, a.signers or os.path.join(a.state, "allowed_signers"), a.state,
                   a.mark, not a.no_replay_check, a.allow_legacy, a.max_age_hours)
    except Reject as e:
        print("REJECT: %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
