from aws_cdk import Stack
from aws_cdk.aws_dynamodb import Table
from aws_cdk.aws_lambda import Runtime, Tracing
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from aws_cdk.aws_secretsmanager import Secret
from constructs import Construct
from cdklabs.generative_ai_cdk_constructs.bedrock import (
    Agent,
    BedrockFoundationModel,
    AgentActionGroup,
    ActionGroupExecutor,
    Guardrail,
    Topic,
    ApiSchema,
)


class AiAgentStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        secret: Secret,
        invoke_agent_lambda: PythonFunction,
        ecommerce_table: Table,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        agent_lambda_function = PythonFunction(
            self,
            "AgentLambdaFunction",
            runtime=Runtime.PYTHON_3_11,
            tracing=Tracing.ACTIVE,
            entry="./agent",
            index="app.py",
            handler="lambda_handler",
        )
        secret.grant_read(agent_lambda_function)
        agent_lambda_function.add_environment(
            "ECOMMERCE_TABLE_NAME", ecommerce_table.table_name
        )
        # Bedrock AI Agent
        agent = Agent(
            self,
            "Agent",
            foundation_model=BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
            instruction="You are a helpful and friendly AI assistant.",
        )
        executor_group = ActionGroupExecutor(lambda_=agent_lambda_function)

        # agent action group

        action_group = AgentActionGroup(
            self,
            "ActionGroup",
            action_group_name="GreatCustomerSupport",
            description="Use these functions for customer support",
            action_group_executor=executor_group,
            action_group_state="ENABLED",
            api_schema=ApiSchema.from_asset("./agent/openapi.json"),
        )

        ecommerce_table.grant_full_access(agent_lambda_function)

        agent.add_alias(
            alias_name="grocery_agent_alias", description="Alias for description"
        )

        agent.add_action_group(action_group)

        # Guardrails
        agent_guardrail = Guardrail(
            self,
            id="grocery-agent-guardrail-001",
            name="GroceryAgentManagementGuardrail",
            description="Guardrails for secure interactions.",
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
        )
        agent.add_guardrail(agent_guardrail)

        invoke_agent_lambda.add_environment("AGENT_ID", agent.agent_id)
        # invoke_agent_lambda.add_environment("AGENT_ALIAS", agent.alias_id)
