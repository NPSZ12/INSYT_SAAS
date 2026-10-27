import json
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from apc.config import Settings
from apc.db import LedgerDB
from apc.adapters.email.pst_backend import PstMessage
from apc.stages.container_expansion import run_container_expansion


STAMP = "2026-10-27T12:00:00Z"
JOB = "JOB-EMAIL-LEDGER"
PARENT = "FILE-PST-ROOT"


def make_email(sender, message_id, attachment=None):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "legal@example.test"
    msg["Subject"] = "Discovery Family Test"
    msg["Message-ID"] = message_id
    msg.set_content("Identical message body for duplicate tests.")

    if attachment:
        msg.add_attachment(
            b"Unique attachment data",
            maintype="application",
            subtype="octet-stream",
            filename=attachment,
        )

    return msg.as_bytes()


def mock_pst_messages(self, pst_path):
    yield PstMessage(
        folder_path="Inbox",
        subject="Discovery Family Test",
        sender="alice@example.test",
        to="legal@example.test",
        message_id="<one@example.test>",
        raw_eml_bytes=make_email(
            "alice@example.test",
            "<one@example.test>",
            "alice_attachment.txt",
        ),
    )

    yield PstMessage(
        folder_path="Inbox",
        subject="Discovery Family Test",
        sender="bob@example.test",
        to="legal@example.test",
        message_id="<two@example.test>",
        raw_eml_bytes=make_email(
            "bob@example.test",
            "<two@example.test>",
            "bob_attachment.txt",
        ),
    )

    yield PstMessage(
        folder_path="Sent Items",
        subject="Independent Message",
        sender="legal@example.test",
        to="outside@example.test",
        message_id="<three@example.test>",
        raw_eml_bytes=make_email(
            "legal@example.test",
            "<three@example.test>",
        ),
    )


class EmailFamilyLedgerRegression(unittest.TestCase):

    def test_pst_eml_attachment_ledger_lineage(self):
        with tempfile.TemporaryDirectory(
            prefix="insyt_email_ledger_"
        ) as temp:
            root = Path(temp)
            input_dir = root / "input"
            input_dir.mkdir()

            pst = input_dir / "synthetic_mailbox.pst"
            pst.write_bytes(b"SYNTHETIC_BACKEND_FIXTURE")

            db = LedgerDB(str(root / "ledger.sqlite"))
            db.init_schema()

            try:
                db.execute(
                    """
                    INSERT INTO processing_job (
                        job_id, matter_id, client_id,
                        created_at, status
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        JOB,
                        "MATTER-TEST",
                        "CLIENT-TEST",
                        STAMP,
                        "pending",
                    ),
                )

                db.execute(
                    """
                    INSERT INTO file_processing_metrics (
                        file_id, matter_id, job_id,
                        original_path, normalized_path,
                        extension, mime_type, source_bytes,
                        is_container, container_depth,
                        stage_status_json, exception_json,
                        created_at, updated_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, 'pst',
                        'application/vnd.ms-outlook',
                        ?, 0, 0, '{}', '[]', ?, ?
                    )
                    """,
                    (
                        PARENT,
                        "MATTER-TEST",
                        JOB,
                        str(pst),
                        pst.name,
                        pst.stat().st_size,
                        STAMP,
                        STAMP,
                    ),
                )

                with patch(
                    "apc.adapters.email.readpst_backend."
                    "ReadPstBackend.iter_messages",
                    mock_pst_messages,
                ):
                    run_container_expansion(
                        db=db,
                        settings=Settings(),
                        job_id=JOB,
                        matter_id="MATTER-TEST",
                        input_dir=str(input_dir),
                    )

                rows = [
                    dict(row)
                    for row in db.query(
                        """
                        SELECT *
                        FROM file_processing_metrics
                        WHERE job_id=?
                        """,
                        (JOB,),
                    )
                ]

                by_id = {
                    row["file_id"]: row
                    for row in rows
                }

                pst_children = [
                    row for row in rows
                    if row["parent_file_id"] == PARENT
                    and str(row["extension"]).lstrip(".") == "eml"
                ]

                self.assertEqual(
                    len(pst_children), 3,
                    "PST must register three separate EML files.",
                )

                file_ids = {
                    row["file_id"] for row in pst_children
                }

                self.assertEqual(len(file_ids), 3)

                family_ids = {
                    row["family_id"] for row in pst_children
                }

                self.assertEqual(
                    len(family_ids), 3,
                    "Each PST message needs its own family.",
                )

                for row in pst_children:
                    self.assertEqual(
                        row["family_id"],
                        row["file_id"],
                        "PST EML must start its own family.",
                    )

                    self.assertTrue(
                        Path(row["original_path"]).is_file(),
                        "EML native must be preserved.",
                    )

                    stage = json.loads(
                        row["stage_status_json"] or "{}"
                    )

                    relationship = (
                        stage.get("container_expansion", {})
                        .get("relationship")
                    )

                    self.assertEqual(
                        relationship, "mailbox_message"
                    )

                eml_ids = {
                    row["file_id"] for row in pst_children
                }

                attachment_rows = [
                    row for row in rows
                    if row["parent_file_id"] in eml_ids
                ]

                self.assertEqual(
                    len(attachment_rows), 2,
                    "Both email attachments need ledger records.",
                )

                attachment_parents = {
                    row["parent_file_id"]
                    for row in attachment_rows
                }

                self.assertEqual(
                    len(attachment_parents), 2,
                    "Attachments must remain with their own emails.",
                )

                for attachment in attachment_rows:
                    parent = by_id[
                        attachment["parent_file_id"]
                    ]

                    self.assertEqual(
                        attachment["family_id"],
                        parent["family_id"],
                        "Attachment must inherit email family.",
                    )

                    self.assertNotEqual(
                        attachment["file_id"],
                        parent["file_id"],
                    )

                    self.assertTrue(
                        Path(
                            attachment["original_path"]
                        ).is_file()
                    )

                print(
                    "PASS: Three EML occurrences registered"
                )
                print(
                    "PASS: Three unique email Family IDs"
                )
                print(
                    "PASS: Two independent attachment records"
                )
                print(
                    "PASS: Correct parent/child family inheritance"
                )
                print(
                    "PASS: Native files preserved"
                )

            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
