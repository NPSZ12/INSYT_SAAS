from __future__ import annotations

import unittest
from unittest.mock import Mock

from apc.azure_job_runner import resolve_azure_completion_status


class AzureCompletionStatusTests(unittest.TestCase):

    def resolve(
        self,
        *,
        status="completed",
        exceptions=0,
        failed_sources=0,
    ):
        db = Mock()
        db.query.side_effect = [
            [{
                "status": status,
                "exception_count": exceptions,
            }],
            [{
                "failed_sources": failed_sources,
            }],
        ]

        result = resolve_azure_completion_status(
            db=db,
            job_id="SYNTHETIC",
        )

        self.assertEqual(db.query.call_count, 2)
        return result

    def test_clean_job_remains_completed(self):
        status, message = self.resolve()
        self.assertEqual(status, "completed")
        self.assertEqual(
            message,
            "Azure processing job completed.",
        )

    def test_failed_adapter_overrides_clean_job_metrics(self):
        status, message = self.resolve(
            failed_sources=1,
        )
        self.assertEqual(
            status,
            "completed_with_exceptions",
        )
        self.assertIn("exceptions", message)

    def test_existing_stage_exceptions_are_preserved(self):
        status, _ = self.resolve(
            exceptions=2,
        )
        self.assertEqual(
            status,
            "completed_with_exceptions",
        )

    def test_existing_exception_status_is_preserved(self):
        status, _ = self.resolve(
            status="completed_with_exceptions",
        )
        self.assertEqual(
            status,
            "completed_with_exceptions",
        )

    def test_nonterminal_job_cannot_report_completed(self):
        db = Mock()
        db.query.return_value = [{
            "status": "processing",
            "exception_count": 0,
        }]

        with self.assertRaisesRegex(
            RuntimeError,
            "has not completed",
        ):
            resolve_azure_completion_status(
                db=db,
                job_id="SYNTHETIC",
            )

        db.query.assert_called_once()


if __name__ == "__main__":
    unittest.main()