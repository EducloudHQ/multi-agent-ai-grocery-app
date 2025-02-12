from aws_cdk import (
    Stack,
    aws_lambda,
    aws_s3,
    aws_s3_notifications,
    aws_lambda_event_sources as lambda_event_sources,
    aws_stepfunctions as sfn,
    aws_iam as iam,
    aws_appsync as appsync,
    aws_sqs as sqs,
    aws_dynamodb as dynamodb,
    Duration,
    CfnOutput,
)
from cdklabs.generative_ai_cdk_constructs.bedrock import (
    BedrockFoundationModel,
    ActionGroupExecutor,
    ApiSchema,
    AgentActionGroup,
    Agent,
    Guardrail,
    Topic,
)

from constructs import Construct
from aws_cdk.aws_lambda import (
    Runtime,
    FunctionUrlAuthType,
    FunctionUrlCorsOptions,
    HttpMethod,
    InvokeMode,
    Tracing,
)
from aws_cdk.aws_lambda_python_alpha import PythonFunction
import json


class GroceryAiAgentCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Define the DynamoDB table
        ecommerce_table = dynamodb.Table(
            self,
            "GroceryAppTable",
            table_name="GroceryAppTable",
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_IMAGE,
        )

        # AppSync API
        api = appsync.GraphqlApi(
            self,
            "GroceryListAgentApi",
            name="grocery-list-agents-api",
            definition=appsync.Definition.from_schema(
                appsync.SchemaFile.from_asset("graphql/schema.graphql"),
            ),
            log_config=appsync.LogConfig(field_log_level=appsync.FieldLogLevel.ALL),
            authorization_config=appsync.AuthorizationConfig(
                default_authorization=appsync.AuthorizationMode(
                    authorization_type=appsync.AuthorizationType.API_KEY
                )
            ),
        )

        # create products in stripe lambda Function for Resolver
        batch_upload_products_lambda_function = PythonFunction(
            self,
            "BatchUploadProductsLambda",
            runtime=Runtime.PYTHON_3_11,
            entry="./batch_upload_products",
            index="batch_upload_products.py",
            handler="handler",
        )
        # create products in stripe lambda Function for Resolver
        create_stripe_products_lambda_function = PythonFunction(
            self,
            "CreateStripeProductsLambda",
            runtime=Runtime.PYTHON_3_11,
            entry="./create_stripe_products",
            index="create_stripe_products.py",
            handler="handler",
        )

        action_group_function = PythonFunction(
            self,
            "AgentLambdaFunction",
            runtime=Runtime.PYTHON_3_11,
            tracing=Tracing.ACTIVE,
            entry="./agent",
            index="app.py",
            handler="lambda_handler",
        )
        action_group_function.add_environment(
            "ECOMMERCE_TABLE_NAME", ecommerce_table.table_name
        )
        # create products in stripe lambda Function for Resolver
        invoke_agent_lambda = PythonFunction(
            self,
            "InvokeGroceryListAgent",
            runtime=Runtime.PYTHON_3_11,
            entry="./agent",
            index="invoke_agent.py",
            handler="handler",
            timeout=Duration.seconds(300),
        )

        invoke_agent_lambda_url = invoke_agent_lambda.add_function_url(
            auth_type=FunctionUrlAuthType.NONE,  # Public access
            invoke_mode=InvokeMode.RESPONSE_STREAM,
            cors=FunctionUrlCorsOptions(
                allowed_origins=["*"],  # Allow all origins
                allowed_methods=[HttpMethod.GET],  # Allow GET requests
            ),
        )

        invoke_agent_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeAgent",
                    "bedrock:RetrieveAndGenerate",
                    "bedrock:Retrieve",
                    "bedrock:ListAgents",
                    "bedrock:GetAgent",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
                # Grant access to all Bedrock models
            )
        )

        # Grant Lambda access to DynamoDB
        ecommerce_table.grant_write_data(batch_upload_products_lambda_function)
        batch_upload_products_lambda_function.add_environment(
            "ECOMMERCE_TABLE_NAME", ecommerce_table.table_name
        )
        # Add Lambda as a DataSource for AppSync
        lambda_ds = api.add_lambda_data_source(
            "LambdaDataSource", batch_upload_products_lambda_function
        )

        # Define the Resolver for the uploadProducts Mutation
        lambda_ds.create_resolver(
            id="BatchUploadProductsResolver",
            type_name="Mutation",
            field_name="batchUploadProducts",
            request_mapping_template=appsync.MappingTemplate.lambda_request(),
            response_mapping_template=appsync.MappingTemplate.lambda_result(),
        )
        # Add Lambda as a DataSource for AppSync
        create_stripe_products_lambda_ds = api.add_lambda_data_source(
            "CreateStripeProductsLambdaDataSource",
            create_stripe_products_lambda_function,
        )

        # Define the Resolver for the uploadProducts Mutation
        create_stripe_products_lambda_ds.create_resolver(
            id="CreateStripeProductsResolver",
            type_name="Mutation",
            field_name="createStripeProducts",
            request_mapping_template=appsync.MappingTemplate.lambda_request(),
            response_mapping_template=appsync.MappingTemplate.lambda_result(),
        )

        # Add Global Secondary Indexes (GSIs)
        ecommerce_table.add_global_secondary_index(
            index_name="userOrders",
            partition_key=dynamodb.Attribute(
                name="GSI1PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        ecommerce_table.add_global_secondary_index(
            index_name="orderProducts",
            partition_key=dynamodb.Attribute(
                name="GSI2PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI2SK", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # create products in stripe lambda Function for Resolver
        trigger_step_function_products_lambda_function = PythonFunction(
            self,
            "TriggerStepFunctionsWorkflow",
            runtime=Runtime.PYTHON_3_11,
            entry="./step_functions_workflow_trigger",
            index="step_functions_workflow_trigger.py",
            handler="handler",
        )

        grocery_list_bucket = aws_s3.Bucket(
            self,
            "grocery-list-bucket",
            versioned=False,
            encryption=aws_s3.BucketEncryption.S3_MANAGED,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
        )

        # Step 3: Grant the Lambda function permissions to read from the S3 bucket
        grocery_list_bucket.grant_read_write(
            trigger_step_function_products_lambda_function
        )
        # Add an S3 event notification to trigger the Lambda function

        # Step 4: Grant the Lambda function permissions to use Textract
        textract_policy = iam.PolicyStatement(
            actions=[
                "textract:DetectDocumentText",
                "textract:StartDocumentTextDetection",
                "textract:GetDocumentTextDetection",
            ],
            resources=["*"],  # Grant access to all Textract resources
        )
        trigger_step_function_products_lambda_function.add_to_role_policy(
            textract_policy
        )
        # Step 5: Add an S3 event trigger to invoke the Lambda function
        notification = aws_s3_notifications.LambdaDestination(
            trigger_step_function_products_lambda_function
        )
        grocery_list_bucket.add_event_notification(
            aws_s3.EventType.OBJECT_CREATED, notification
        )

        # Step 5: Create a Dead-Letter Queue (DLQ) for the SQS queue
        dlq = sqs.Queue(
            self, "GroceryListDLQ", retention_period=Duration.days(14)
        )  # Retain messages for 14 days

        # Step 6: Create the main SQS queue with a DLQ
        sqs_queue = sqs.Queue(
            self,
            "GroceryListTextExtractionQueue",
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,  # Retry 3 times before sending to DLQ
            ),
        )

        # Step 7: Grant the first Lambda function permissions to send messages to the SQS queue
        sqs_queue.grant_send_messages(trigger_step_function_products_lambda_function)

        # Step 8: Set the SQS queue URL as an environment variable for the Lambda function
        trigger_step_function_products_lambda_function.add_environment(
            "SQS_QUEUE_URL", sqs_queue.queue_url
        )

        # Step 10: Create the second Lambda function (SQS Poller)
        sqs_poller_lambda = PythonFunction(
            self,
            "LambdaSQSPoller",
            runtime=aws_lambda.Runtime.PYTHON_3_11,
            handler="handler",
            index="lambda_sqs_poller.py",
            entry="./sqs_poller",
            timeout=Duration.seconds(30),
        )

        # Step 11: Grant the second Lambda function permissions to poll the SQS queue
        sqs_queue.grant_consume_messages(sqs_poller_lambda)

        sqs_poller_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"],  # Grant access to all Bedrock models
            )
        )

        # Step 11: Add an SQS event source mapping to trigger the Lambda function
        sqs_event_source = lambda_event_sources.SqsEventSource(sqs_queue)
        sqs_poller_lambda.add_event_source(sqs_event_source)

        sqs_poller_lambda.add_environment("SQS_QUEUE_URL", sqs_queue.queue_url)

        # Step 5: (Optional) Output the bucket name and Lambda function ARN
        self.bucket_name = grocery_list_bucket.bucket_name
        self.lambda_arn = trigger_step_function_products_lambda_function.function_arn
        self.sqs_queue_url = sqs_queue.queue_url
        self.sqs_poller_lambda_arn = sqs_poller_lambda.function_arn
        self.dlq_url = dlq.queue_url

        agent = Agent(
            self,
            "Agent",
            foundation_model=BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
            instruction="You are a helpful and friendly AI assistant designed to assist users with a variety of tasks, including telling the current time, creating Stripe payment links, batch uploading product lists into a DynamoDB table, and scheduling meetings.",
        )

        executor_group = ActionGroupExecutor(lambda_=action_group_function)

        action_group = AgentActionGroup(
            self,
            "ActionGroup",
            action_group_name="GreatCustomerSupport",
            description="Use these functions for customer support",
            action_group_executor=executor_group,
            action_group_state="ENABLED",
            api_schema=ApiSchema.from_asset("./agent/openapi.json"),
        )

        ecommerce_table.grant_full_access(action_group_function)
        action_group_function.add_environment(
            "ECOMMERCE_TABLE_NAME", ecommerce_table.table_name
        )

        agent.add_alias(
            alias_name="grocery_agent_alias", description="Alias for description"
        )

        agent.add_action_group(action_group)
        agent_guardrail = Guardrail(
            self,
            name="GroceryAgentManagementGuardrail",
            description="Guardrails to ensure secure and compliant interactions with Stripe and DynamoDB.",
            denied_topics=[
                Topic(
                    name="FinancialFraud",
                    examples=[
                        "Requests to create fake products, or generate unauthorized payment links."
                    ],
                    definition="Prevent any actions that could lead to fraud or misuse of Stripe's payment system.",
                ),
                Topic(
                    name="DataLeakage",
                    examples=[
                        "Requests to expose sensitive customer data, such as credit card numbers or PII."
                    ],
                    definition="Block any actions that could result in the leakage of sensitive or (PII).",
                ),
                Topic(
                    name="UnauthorizedAccess",
                    examples=[
                        "Requests to access or modify products or payment links without proper authentication."
                    ],
                    definition="Prevent unauthorized access to Stripe or DynamoDB resources.",
                ),
                Topic(
                    name="MaliciousCodeExecution",
                    examples=[
                        "Requests to execute code, scripts, or commands on the server or database."
                    ],
                    definition="Block any attempts to execute malicious code or scripts.",
                ),
            ],
            blocked_outputs_messaging="Your request cannot be processed due to security restrictions.",
            blocked_input_messaging="Your input contains restricted content. Please revise your request.",
            id="grocery-agent-guardrail-001",
        )
        agent.add_guardrail(agent_guardrail)

        invoke_agent_lambda.add_environment("AGENT_ID", agent.agent_id)
        # invoke_agent_lambda.add_environment("AGENT_ALIAS", agent.alias_id)

        # Load the ASL definition from the JSON file
        with open("./state_machine/state_machine_definition.json", "r") as file:
            state_machine_definition = json.load(file)

        # Create the Step Functions state machine using the ASL definition
        state_machine = sfn.StateMachine(
            self,
            "GroceryDocumentTextractStateMachine",
            definition_body=sfn.DefinitionBody.from_string(
                json.dumps(state_machine_definition)
            ),
            # Use definition_body
            state_machine_type=sfn.StateMachineType.STANDARD,
        )

        # Grant the Lambda function permissions to send task success/failure
        state_machine.grant_task_response(sqs_poller_lambda)

        trigger_step_function_products_lambda_function.add_environment(
            "STATE_MACHINE_ARN", state_machine.state_machine_arn
        )

        # Optionally, grant the Lambda function permissions to start executions
        state_machine.grant_start_execution(sqs_poller_lambda)

        state_machine.grant_start_execution(
            trigger_step_function_products_lambda_function
        )
        invoke_agent_lambda.grant_invoke(state_machine)

        # Grant the state machine permissions to interact with S3
        grocery_list_bucket.grant_read_write(state_machine)

        # Grant the state machine permissions to use Textract
        state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "textract:StartDocumentTextDetection",
                    "textract:GetDocumentTextDetection",
                    "textract:DetectDocumentText",
                ],
                resources=["*"],  # Textract does not support resource-level permissions
            )
        )

        # Grant the state machine permissions to send messages to the SQS queue
        sqs_queue.grant_send_messages(state_machine)

        # Output the AppSync GraphQL Endpoint
        CfnOutput(self, "GraphQLEndpoint", value=api.graphql_url)
        (CfnOutput(self, "GraphQLApiKey", value=api.api_key),)

        CfnOutput(self, "InvokeAgentFunctionUrl", value=invoke_agent_lambda_url.url)
