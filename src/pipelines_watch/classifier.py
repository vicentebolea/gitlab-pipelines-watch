from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

SYSTEM = (
    "You are a CI expert. A GitLab CI job failed with script_failure. Decide whether the failure is "
    "transient (network, registry, runner resource exhaustion, known flaky test: worth retrying) or a "
    "genuine code/configuration bug (not worth retrying). Past failures with their job, platform and observed outcome "
    "are given; the same error can be transient on one platform and a bug on another; weigh them heavily: 'retry_passed' means a retry succeeded, 'retry_failed' means it "
    "failed again."
)

PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", "Similar past failures:\n{examples}\n\nJob: {job_name} ({platform})\n\nError ({error_type}):\n{log}"),
])


class Decision(BaseModel):
    retry: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(description="one short sentence")


def build_chain(llm_model):
    return PROMPT | init_chat_model(llm_model).with_structured_output(Decision, method="json_schema")


def format_examples(docs):
    return "\n\n".join(d.metadata["markdown"] for d in docs) or "(none)"
