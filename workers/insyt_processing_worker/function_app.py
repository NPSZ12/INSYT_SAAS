import logging

import azure.functions as func

from app.workers.processing_worker import process_job_message


app = func.FunctionApp()


@app.queue_trigger(
    arg_name="msg",
    queue_name="insyt-processing-jobs",
    connection="AzureWebJobsStorage",
)
def processing_queue_worker(msg: func.QueueMessage):
    message_body = msg.get_body().decode("utf-8")

    logging.info("INSYT processing worker received queue message.")
    logging.info(message_body)

    process_job_message(message_body)

    logging.info("INSYT processing worker completed queue message.")