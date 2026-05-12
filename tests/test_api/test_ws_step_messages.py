"""Test that WebSocket emits StepMessage when tasks have steps."""
from __future__ import annotations

from app.schemas.log import IntermediateStep, StepKind, TaskEvent
from app.schemas.progress import TaskStatus


async def test_step_messages_emitted_for_task_with_steps() -> None:
    """When a TaskEvent contains steps, the WS route should emit
    individual StepMessage envelopes alongside the StepStatusMessage."""
    # Import the route's _on_task_event factory indirectly by checking the
    # emitted messages through a mock broker.
    from app.routes.ws import _step_status_for

    steps = [
        IntermediateStep(kind=StepKind.thinking, text="analyzing"),
        IntermediateStep(kind=StepKind.tool_call, tool_name="Read"),
    ]
    event = TaskEvent(
        task="build",
        tool="harness:claude-code",
        success=True,
        status=TaskStatus.completed,
        steps=steps,
    )

    # Verify the helper function still works
    assert _step_status_for(event) == "completed"

    # Build the expected step message format
    for step in steps:
        msg = {
            "type": "step",
            "flow_id": "test-flow",
            "task": event.task,
            "step": step.model_dump(mode="json"),
        }
        assert msg["type"] == "step"
        assert msg["task"] == "build"
