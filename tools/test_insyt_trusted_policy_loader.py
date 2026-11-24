"""Tests for pinned INSYT policy-source retrieval."""

import json
import unittest

from insyt_trusted_policy_loader import (
    BRANCH,
    POLICY_FILE,
    REPOSITORY,
    PolicySourceDenied,
    check_policy_identity,
    read_live_policy,
)


class FakeGit:

    def __init__(self, live, fetched=None, policy=None):
        self.live = live
        self.fetched = fetched or live
        self.policy = policy
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)

        if args == ("remote", "get-url", "origin"):
            return REPOSITORY

        if args == ("ls-remote", "--heads", "origin", BRANCH):
            return f"{self.live}\t{BRANCH}"

        if args == ("fetch", "--no-tags", "origin", BRANCH):
            return ""

        if args == ("rev-parse", "FETCH_HEAD"):
            return self.fetched

        if args == ("show", self.live + ":" + POLICY_FILE):
            if self.policy is None:
                raise PolicySourceDenied("missing record")
            return json.dumps(self.policy)

        raise AssertionError("Unexpected Git operation: " + repr(args))


class TrustedPolicyRetrievalTests(unittest.TestCase):

    def setUp(self):
        self.sha = "a" * 40
        self.policy = {
            "schema_version": 1,
            "approved_scopes": [],
        }

    def test_matching_pinned_policy_loads(self):
        fake = FakeGit(self.sha, policy=self.policy)
        self.assertEqual(read_live_policy(self.sha, fake), self.policy)

    def test_changed_live_policy_rejected(self):
        fake = FakeGit("b" * 40, policy=self.policy)
        with self.assertRaises(PolicySourceDenied):
            read_live_policy(self.sha, fake)
        self.assertFalse(any(c[0] == "fetch" for c in fake.calls))

    def test_policy_changes_during_fetch_rejected(self):
        fake = FakeGit(
            self.sha,
            fetched="b" * 40,
            policy=self.policy,
        )
        with self.assertRaises(PolicySourceDenied):
            read_live_policy(self.sha, fake)

    def test_missing_approval_record_rejected(self):
        fake = FakeGit(self.sha)
        with self.assertRaises(PolicySourceDenied):
            read_live_policy(self.sha, fake)

    def test_invalid_trusted_revision_rejected(self):
        with self.assertRaises(PolicySourceDenied):
            check_policy_identity("not-a-sha", self.sha)

    def test_wrong_origin_rejected(self):
        fake = FakeGit(self.sha, policy=self.policy)

        def wrong_origin(*args):
            if args == ("remote", "get-url", "origin"):
                return "https://example.com/untrusted.git"
            return fake(*args)

        with self.assertRaises(PolicySourceDenied):
            read_live_policy(self.sha, wrong_origin)


if __name__ == "__main__":
    unittest.main()
