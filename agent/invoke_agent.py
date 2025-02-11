import json
import os

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes.appsync import scalar_types_utils

# Initialize Clients
bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime", region_name="us-east-1")
logger = Logger(service="invoke_agent")
agent_id = os.environ.get("AGENT_ID")
agent_alias = os.environ.get("AGENT_ALIAS")
def generate_stream(event_stream):
    """
    Generator function to process streamed data from AWS Bedrock Agent.
    """
    for event in event_stream:
        if 'chunk' in event:
            data = event['chunk']['bytes']
            agent_answer = data.decode('utf8')
            logger.info(f"Chunk Data: {agent_answer}")
            yield agent_answer
        elif 'trace' in event:
            logger.info(f"Trace Event: {json.dumps(event['trace'], indent=2)}")
        else:
            logger.error(f"Unexpected Event Format: {event}")
            raise ValueError("Unexpected event format in EventStream")

def handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event, indent=2)}")

        # Parse the event body
        event_body = json.loads(event['body'])
        logger.info(f"Received event body: {event_body}")

        # Extract grocery_list and validate
        grocery_list = event_body.get("grocery_list")
        if not grocery_list:
            raise ValueError("Error: `grocery_list` is missing or empty.")

        # Create query string
        query = f"Create and return a single Stripe payment link with the list of products: {grocery_list}"

        # Generate a unique session ID
        session_id = scalar_types_utils.make_id()

        # Invoke the Bedrock Agent
        agent_response = bedrock_agent_runtime_client.invoke_agent(
            inputText=query,
            agentId=agent_id,
            agentAliasId=agent_alias,
            sessionId=session_id,
            enableTrace=True,
        )

        # Ensure the response contains the event stream
        if "completion" not in agent_response:
            raise Exception("Agent response is missing `completion` field.")

        event_stream = agent_response["completion"]

        # Collect all chunks from the stream
        final_response = ""
        for chunk in generate_stream(event_stream):
            final_response += chunk

        # Return the final response to API Gateway
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps({"response": final_response}),
        }

    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps({"error": str(e)}),
        }