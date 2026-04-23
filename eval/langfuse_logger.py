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
            host=os.getenv(
                "LANGFUSE_BASE_URL",
                os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            ),
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
) -> tuple[str, str]:
    client = get_client()

    trace = client.start_span(
        trace_context={"trace_id": trace_id},
        name=f"tau2-retail-task-{task_id}",
    )
    trace.update_trace(
        name=f"tau2-retail-task-{task_id}",
        input={"task_id": task_id, "turns": len(turns)},
        output={"pass_fail": "pass" if pass_fail else "fail"},
        metadata={
            "task_id": task_id,
            "model": model,
            "pass_fail": "pass" if pass_fail else "fail",
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "turn_count": len(turns),
        },
    )

    for i, turn in enumerate(turns):
        turn_span = trace.start_span(
            name=f"turn_{i}",
            input=turn.get("input", ""),
            output=turn.get("output", ""),
            metadata={"role": turn.get("role", "unknown")}
        )
        turn_span.end()

    trace.end()

    client.flush()

    actual_trace_id = trace.trace_id
    url = client.get_trace_url(trace_id=actual_trace_id)
    return actual_trace_id, url
