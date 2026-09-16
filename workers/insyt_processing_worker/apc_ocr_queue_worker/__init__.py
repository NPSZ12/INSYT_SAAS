import logging

import azure.functions as func

from app.workers.ocr_worker import process_ocr_set_message


def main(msg: func.QueueMessage) -> None:
    message_body = msg.get_body().decode("utf-8")

    logging.info("APC OCR worker received queue message.")

    process_ocr_set_message(message_body)

    logging.info("APC OCR worker completed queue message.")