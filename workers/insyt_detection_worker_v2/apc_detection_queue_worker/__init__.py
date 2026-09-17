import logging

import azure.functions as func

from app.workers.detection_worker import process_detection_message


def main(msg: func.QueueMessage) -> None:
    message_body = msg.get_body().decode("utf-8")

    logging.info(
        "INSYT Detection Worker V2 received queue message."
    )

    process_detection_message(message_body)

    logging.info(
        "INSYT Detection Worker V2 completed queue message."
    )
