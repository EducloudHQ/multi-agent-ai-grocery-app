import aws_cdk as core
import aws_cdk.assertions as assertions

from grocery_ai_agent_cdk.grocery_ai_agent_cdk_stack import GroceryAiAgentCdkStack

# example tests. To run these tests, uncomment this file along with the example
# resource in grocery_ai_agent_cdk/grocery_ai_agent_cdk_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = GroceryAiAgentCdkStack(app, "grocery-ai-agent-cdk")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
