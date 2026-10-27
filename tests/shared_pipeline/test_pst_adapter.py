import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path

from apc.adapters.base import AdapterContext
from apc.adapters.builtin import register_builtin_adapters
from apc.adapters.dispatcher import dispatch_to_adapter
from apc.adapters.email.pst_adapter import PstAdapter
from apc.adapters.email.pst_backend import PstMessage


class SyntheticPstBackend:
    name = "synthetic-pst-test"

    def iter_messages(self, pst_path):
        yield PstMessage(
            folder_path="Inbox",
            subject="Duplicate Body Test",
            sender="alice@example.test",
            to="legal@example.test",
            message_id="<message-one@example.test>",
            plain_body="Same sensitive message body.",
        )
        yield PstMessage(
            folder_path="Inbox",
            subject="Duplicate Body Test",
            sender="bob@example.test",
            to="legal@example.test",
            message_id="<message-two@example.test>",
            plain_body="Same sensitive message body.",
        )
        yield PstMessage(
            folder_path="Sent Items",
            subject="Third Message",
            sender="legal@example.test",
            to="outside@example.test",
            message_id="<message-three@example.test>",
            plain_body="Independent third message.",
        )


class FailingPstBackend:
    name = "synthetic-pst-failure"

    def iter_messages(self, pst_path):
        raise RuntimeError("SIMULATED_PST_BACKEND_FAILURE")
        yield


class PstAdapterRegression(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        register_builtin_adapters()

    def test_message_identity_and_failure_isolation(self):
        with tempfile.TemporaryDirectory(
            prefix="insyt_pst_regression_"
        ) as temp:
            root = Path(temp)
            source = root / "synthetic.pst"
            source.write_bytes(b"SYNTHETIC_PST_TEST_ONLY")

            context = AdapterContext(
                job_id="JOB-PST-LOCAL",
                matter_id="MATTER-PST-LOCAL",
                file_id="FILE-PST-PARENT",
                source_path=source,
                normalized_path=source.name,
                extension=".pst",
                work_dir=root / "pst_output",
            )

            result = PstAdapter(
                backend=SyntheticPstBackend()
            ).process(context)

            self.assertEqual(result.status, "completed")
            self.assertEqual(len(result.children), 3)
            self.assertEqual(result.metadata["message_count"], 3)

            senders = [
                "alice@example.test",
                "bob@example.test",
                "legal@example.test",
            ]

            message_ids = []

            for index, child in enumerate(result.children):
                self.assertTrue(child.source_path.is_file())
                self.assertEqual(child.extension, ".eml")
                self.assertEqual(
                    child.relationship, "mailbox_message"
                )
                self.assertTrue(child.start_new_family)

                message = BytesParser(
                    policy=policy.default
                ).parsebytes(child.source_path.read_bytes())

                self.assertEqual(
                    str(message["From"]), senders[index]
                )

                self.assertTrue(str(message["To"]))

                message_ids.append(
                    str(message["Message-ID"])
                )

                eml_result = dispatch_to_adapter(
                    AdapterContext(
                        job_id="JOB-PST-LOCAL",
                        matter_id="MATTER-PST-LOCAL",
                        file_id=f"FILE-EML-{index + 1}",
                        source_path=child.source_path,
                        normalized_path=child.normalized_path,
                        extension=".eml",
                        work_dir=root / f"eml_output_{index + 1}",
                    )
                )

                self.assertIsNotNone(eml_result)
                self.assertIn(
                    eml_result.status,
                    {"completed", "completed_with_warnings"},
                )

            self.assertEqual(
                len(set(message_ids)), 3
            )

            failed = PstAdapter(
                backend=FailingPstBackend()
            ).process(context)

            self.assertEqual(failed.status, "failed")
            self.assertIn(
                "SIMULATED_PST_BACKEND_FAILURE",
                failed.error,
            )

            recovery = dispatch_to_adapter(
                AdapterContext(
                    job_id="JOB-PST-LOCAL",
                    matter_id="MATTER-PST-LOCAL",
                    file_id="FILE-RECOVERY",
                    source_path=result.children[0].source_path,
                    normalized_path=result.children[0].normalized_path,
                    extension=".eml",
                    work_dir=root / "recovery_output",
                )
            )

            self.assertIsNotNone(recovery)
            self.assertEqual(recovery.status, "completed")


if __name__ == "__main__":
    unittest.main()
