from aws_cdk import Stack, Duration, aws_sqs as sqs

from constructs import Construct


class SQSStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        # Step 5: Create a Dead-Letter Queue (DLQ) for the SQS queue
        super().__init__(scope, construct_id, **kwargs)
        dlq = sqs.Queue(
            self, "GroceryListDLQ", retention_period=Duration.days(14)
        )  # Retain messages for 14 days

        # Step 6: Create the main SQS queue with a DLQ
        self.sqs_queue = sqs.Queue(
            self,
            "GroceryListTextExtractionQueue",
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,  # Retry 3 times before sending to DLQ
            ),
        )
