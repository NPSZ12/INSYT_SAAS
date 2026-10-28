from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WORKER = ROOT / "workers" / "insyt_detection_worker_v2"

sys.path.insert(0, str(WORKER))

from apc.detection.discovery_rules import (
    load_discovery_rules_from_file,
)
from apc.detection.engine import run_detection_engine


WORKBOOK = (
    ROOT
    / "tests"
    / "shared_pipeline"
    / "fixtures"
    / "Discovery_Search_Rules.xlsx"
)


class DiscoveryRuleIsolationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not WORKBOOK.exists():
            raise RuntimeError(
                f"Missing Discovery workbook: {WORKBOOK}"
            )

    def detect(self, text, sheets):
        rules = load_discovery_rules_from_file(
            WORKBOOK,
            sheet_names=sheets,
        )

        result = run_detection_engine(
            text,
            enable_azure=False,
            enable_structured_rules=True,
            structured_rules=rules,
            include_phi=False,
        )

        return result["candidates"]

    def test_pii_only_is_not_responsive(self):
        text = (
            "Customer information: "
            "Jane Example, 423-555-0123, "
            "123-45-6789, jane@example.com."
        )

        candidates = self.detect(
            text,
            ["General Responsiveness"],
        )

        self.assertEqual(
            len(candidates),
            0,
            "PII-only text generated Discovery hits.",
        )

    def test_transaction_terms_are_responsive(self):
        text = (
            "The acquisition agreement was amended "
            "before closing the transaction."
        )

        candidates = self.detect(
            text,
            ["General Responsiveness"],
        )

        self.assertTrue(
            candidates,
            "Expected transaction responsiveness hit.",
        )

    def test_privilege_terms_generate_flag(self):
        text = (
            "Outside counsel provided legal advice "
            "regarding pending litigation. "
            "Attorney-client privileged communication."
        )

        candidates = self.detect(
            text,
            ["Privilege"],
        )

        self.assertTrue(
            any(
                candidate.entity_type == "Privilege"
                for candidate in candidates
            ),
            "Expected a privilege indicator.",
        )


if __name__ == "__main__":
    unittest.main()
