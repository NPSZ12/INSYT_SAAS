import unittest

from json_native_job_completion import (
    JsonSourceJobNotComplete,
    require_completed_json_source_job,
)


APC_ID = "JOB-APC-123"
TRACKED_ID = "JOB-TRACKED-456"


def history(status="completed"):
    return {
        "jobs": [{
            "job_id": TRACKED_ID,
            "apc_job_id": APC_ID,
            "status": status,
        }]
    }


class JobCompletionTests(unittest.TestCase):

    def resolve(self, rows=None):
        return require_completed_json_source_job(
            apc_job_id=APC_ID,
            history=history() if rows is None else rows,
        )

    def test_completed_job(self):
        result = self.resolve()
        self.assertEqual(result["apc_job_id"], APC_ID)
        self.assertEqual(result["tracked_job_id"], TRACKED_ID)
        self.assertTrue(result["completed"])

    def test_completed_with_exceptions(self):
        result = self.resolve(
            history("completed_with_exceptions")
        )
        self.assertTrue(result["completed"])

    def test_incomplete_statuses_rejected(self):
        for status in (
            "queued", "processing", "failed",
            "cancelled", ""
        ):
            with self.subTest(status=status):
                with self.assertRaises(JsonSourceJobNotComplete):
                    self.resolve(history(status))

    def test_missing_job_rejected(self):
        with self.assertRaises(JsonSourceJobNotComplete):
            self.resolve({"jobs": []})

    def test_wrong_apc_id_rejected(self):
        rows = {
            "jobs": [{
                "job_id": TRACKED_ID,
                "apc_job_id": "JOB-OTHER",
                "status": "completed",
            }]
        }
        with self.assertRaises(JsonSourceJobNotComplete):
            self.resolve(rows)

    def test_duplicate_mapping_rejected(self):
        rows = history()
        rows["jobs"].append(dict(rows["jobs"][0]))

        with self.assertRaises(JsonSourceJobNotComplete):
            self.resolve(rows)

    def test_missing_tracked_id_rejected(self):
        rows = history()
        rows["jobs"][0]["job_id"] = ""

        with self.assertRaises(JsonSourceJobNotComplete):
            self.resolve(rows)

    def test_missing_history_rejected(self):
        for rows in (None, {}, {"jobs": None}):
            with self.subTest(rows=rows):
                with self.assertRaises(JsonSourceJobNotComplete):
                    require_completed_json_source_job(
                        apc_job_id=APC_ID,
                        history=rows,
                    )


    def test_raw_history_normalized_before_validation(self):
        from json_native_job_completion import (
            require_completed_json_source_job_from_history,
        )

        raw = {
            "jobs": [{
                "job_id": TRACKED_ID,
                "routing": {"job_id": APC_ID},
                "status": "completed",
            }]
        }

        def normalize(job):
            return {
                **job,
                "apc_job_id": job["routing"]["job_id"],
            }

        result = require_completed_json_source_job_from_history(
            apc_job_id=APC_ID,
            history=raw,
            normalize_job=normalize,
        )

        self.assertTrue(result["completed"])
        self.assertEqual(result["tracked_job_id"], TRACKED_ID)

    def test_normalization_failure_blocks_promotion(self):
        from json_native_job_completion import (
            require_completed_json_source_job_from_history,
        )

        with self.assertRaises(JsonSourceJobNotComplete):
            require_completed_json_source_job_from_history(
                apc_job_id=APC_ID,
                history=history(),
                normalize_job=lambda job: None,
            )

    def test_history_read_errors_block_promotion(self):
        from json_native_job_completion import (
            require_completed_json_source_job_from_history,
        )

        raw = history()
        raw["errors"] = [{"type": "read_failure"}]

        with self.assertRaises(JsonSourceJobNotComplete):
            require_completed_json_source_job_from_history(
                apc_job_id=APC_ID,
                history=raw,
                normalize_job=lambda job: job,
            )


if __name__ == "__main__":
    unittest.main()