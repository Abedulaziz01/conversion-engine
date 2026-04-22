import os
from langfuse import Langfuse
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client():
    global _client
    if _client is None:
        _client = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        )
    return _client


def log_trace(
    trace_id: str,
    task_id: str,
    model: str,
    pass_fail: bool,
    cost: float,
    latency_ms: int,
    turns: list
) -> str:
    client = get_client()

    trace = client.trace(
        id=trace_id,
        name=f"tau2-retail-task-{task_id}",
        metadata={
            "task_id": task_id,
            "model": model,
            "pass_fail": "pass" if pass_fail else "fail",
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "turn_count": len(turns)
        }
    )

    for i, turn in enumerate(turns):
        trace.span(
            name=f"turn_{i}",
            input=turn.get("input", ""),
            output=turn.get("output", ""),
            metadata={"role": turn.get("role", "unknown")}
        )

    client.flush()

    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    url = f"{host}/trace/{trace_id}"
    return url