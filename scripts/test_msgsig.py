# Tests for msgsig.py v2; needs ssh-keygen on PATH. Run: python -m unittest test_msgsig
import contextlib
import datetime
import io
import os
import shutil
import subprocess
import tempfile
import unittest

import msgsig


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = msgsig.main(list(argv))
    return code, out.getvalue()


class MsgsigTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.state = os.path.join(self.d, "state")
        os.makedirs(self.state)
        self.keys = {}
        with open(os.path.join(self.state, "allowed_signers"), "w") as f:
            for h in ("alice", "mallory"):
                k = os.path.join(self.d, h)
                subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", k], check=True)
                self.keys[h] = k
                if h == "alice":
                    f.write('alice namespaces="messaging" ' + open(k + ".pub").read())

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def msg(self, name="m.md", sender="alice", to="bob", extra="", key=None, sign=True):
        p = os.path.join(self.d, name)
        with open(p, "w", newline="\n") as f:
            f.write("from: %s\nto: %s\nsubject: hi\n%s\nbody\n" % (sender, to, extra))
        if sign:
            code, out = run("sign", p, "--key", key or self.keys[sender])
            self.assertEqual(code, 0, out)
        return p

    def verify(self, p, *extra):
        return run("verify", p, "--me", "bob", "--state", self.state, *extra)

    def test_valid_message_returns_ok_and_local_copy(self):
        code, out = self.verify(self.msg())
        self.assertEqual(code, 0, out)
        copy = out.splitlines()[1][len("copy: "):]
        self.assertTrue(copy.startswith(os.path.join(self.state, "verified")))

    def test_sign_adds_date_and_msg_id(self):
        text = open(self.msg()).read()
        self.assertIn("\ndate: ", text)
        self.assertIn("\nmsg-id: alice-", text)

    def test_tampered_body_is_rejected(self):
        p = self.msg()
        with open(p, "a") as f:
            f.write("rm -rf\n")
        self.assertEqual(self.verify(p)[0], 2)

    def test_unpinned_key_is_rejected(self):
        p = self.msg(sender="alice", key=self.keys["mallory"])
        self.assertIn("pinned key", self.verify(p)[1])

    def test_wrong_recipient_is_rejected(self):
        self.assertIn("to:", self.verify(self.msg(to="carol"))[1])

    def test_path_traversal_handle_is_rejected(self):
        p = self.msg(sender="..\\..\\x", sign=False)
        open(p + ".sig", "w").write("x")
        self.assertIn("valid handle", self.verify(p)[1])

    def test_replay_under_new_name_is_rejected_after_mark(self):
        p = self.msg()
        self.assertEqual(self.verify(p, "--mark")[0], 0)
        q = os.path.join(self.d, "copy.md")
        shutil.copyfile(p, q)
        shutil.copyfile(p + ".sig", q + ".sig")
        code, out = self.verify(q, "--mark")
        self.assertEqual(code, 2)
        self.assertIn("replay", out)
        self.assertEqual(self.verify(q, "--no-replay-check")[0], 0)

    def test_old_message_is_rejected(self):
        old = (datetime.datetime.now().astimezone() - datetime.timedelta(hours=30)).isoformat(timespec="seconds")
        self.assertIn("older", self.verify(self.msg(extra="date: " + old + "\n"))[1])

    def test_legacy_header_needs_allow_legacy(self):
        p = self.msg(sign=False)
        subprocess.run(["ssh-keygen", "-Y", "sign", "-f", self.keys["alice"], "-n", "messaging", p],
                       check=True, capture_output=True)
        self.assertEqual(self.verify(p)[0], 2)
        code, out = self.verify(p, "--allow-legacy")
        self.assertEqual(code, 0, out)
        self.assertIn("legacy", out)

    def test_network_paths_are_remote(self):
        self.assertTrue(msgsig.is_remote(r"\\server\share\m.md"))
        self.assertTrue(msgsig.is_remote("//server/share/m.md"))
        self.assertFalse(msgsig.is_remote(self.d))


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.state = os.path.join(self.d, "state")
        os.makedirs(self.state)
        for name in ("ca", "alice", "mallory"):
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", os.path.join(self.d, name)], check=True)
        with open(os.path.join(self.d, "ca.pub")) as f:
            ca_pub = f.read()
        with open(os.path.join(self.state, "allowed_signers"), "w") as f:
            f.write('* cert-authority,namespaces="messaging" ' + ca_pub)
        self.ca = os.path.join(self.d, "ca")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def certify(self, key, handle):
        return run("certify", os.path.join(self.d, key + ".pub"), "--ca", self.ca, "--handle", handle)

    def msg(self, sender, key, name="m.md"):
        p = os.path.join(self.d, name)
        with open(p, "w", newline="\n") as f:
            f.write("from: %s\nto: bob\nsubject: hi\n\nbody\n" % sender)
        code, out = run("sign", p, "--key", os.path.join(self.d, key))
        self.assertEqual(code, 0, out)
        return p, out

    def verify(self, p):
        return run("verify", p, "--me", "bob", "--state", self.state)

    def test_certified_key_verifies(self):
        self.assertEqual(self.certify("alice", "alice")[0], 0)
        p, out = self.msg("alice", "alice")
        self.assertIn("(certificate)", out)
        code, out = self.verify(p)
        self.assertEqual(code, 0, out)

    def test_certificate_for_other_handle_is_rejected(self):
        self.certify("alice", "alice")
        p, _ = self.msg("carol", "alice")
        self.assertEqual(self.verify(p)[0], 2)

    def test_uncertified_key_is_rejected(self):
        p, _ = self.msg("mallory", "mallory")
        self.assertEqual(self.verify(p)[0], 2)

    def test_expired_certificate_is_rejected(self):
        subprocess.run(["ssh-keygen", "-q", "-s", self.ca, "-I", "alice", "-n", "alice",
                        "-V", "20200101:20200102", os.path.join(self.d, "alice.pub")], check=True)
        p, _ = self.msg("alice", "alice")
        self.assertEqual(self.verify(p)[0], 2)

    def test_certify_rejects_invalid_handle(self):
        code, out = self.certify("alice", "..\\x")
        self.assertEqual(code, 2)
        self.assertIn("valid handle", out)


if __name__ == "__main__":
    unittest.main()
