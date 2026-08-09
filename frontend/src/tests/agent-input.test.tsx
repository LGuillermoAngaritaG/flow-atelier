import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
import { AgentInputSection, FlowDrawer } from "@/components/FlowDrawer";
import type { AgentInputRequest } from "@/hooks/useConduit";

// Radix's ScrollArea observes its viewport; jsdom ships no ResizeObserver.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

/**
 * The interactive-harness turn is its own gate: an agent mid-session asking a
 * question, correlated by request id. It shares no state with `tool:hitl`, so
 * it gets its own control rather than borrowing the HITL form.
 */
describe("AgentInputSection", () => {
  afterEach(cleanup);

  const request = { flowId: "f1", requestId: "r-1", prompt: "agent is waiting for your reply:", taskName: "ask" };

  it("shows the prompt and the owning task", () => {
    render(<AgentInputSection agentInput={request} onAnswer={() => {}} />);
    expect(screen.getByText(/agent is waiting for your reply:/)).toBeTruthy();
    expect(screen.getByTestId("agent-input").textContent).toContain("ask");
  });

  it("submits the typed answer", () => {
    const onAnswer = vi.fn();
    render(<AgentInputSection agentInput={request} onAnswer={onAnswer} />);
    fireEvent.change(screen.getByTestId("agent-input-field"), {
      target: { value: "blue" },
    });
    fireEvent.click(screen.getByTestId("agent-input-submit"));
    expect(onAnswer).toHaveBeenCalledWith("blue");
  });

  it("does not submit an empty answer", () => {
    const onAnswer = vi.fn();
    render(<AgentInputSection agentInput={request} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByTestId("agent-input-submit"));
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("keeps the typed answer when the send fails, so it can be retried", () => {
    const onAnswer = vi.fn();
    render(<AgentInputSection agentInput={request} onAnswer={onAnswer} />);
    const field = screen.getByTestId("agent-input-field") as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: "blue" } });
    fireEvent.click(screen.getByTestId("agent-input-submit"));
    expect(field.value).toBe("blue");
  });

  it("starts empty for a different request id, since the key remounts it", () => {
    // The drawer keys each section by requestId, so a new turn is a new
    // component instance — no state to reset by hand.
    const { rerender } = render(
      <AgentInputSection key={request.requestId} agentInput={request} onAnswer={() => {}} />,
    );
    const field = () => screen.getByTestId("agent-input-field") as HTMLTextAreaElement;
    fireEvent.change(field(), { target: { value: "blue" } });
    rerender(
      <AgentInputSection
        key="r-2"
        agentInput={{ flowId: "f1", requestId: "r-2", prompt: "anything else?" }}
        onAnswer={() => {}}
      />,
    );
    expect(field().value).toBe("");
  });
});

/**
 * With max_concurrency > 1, two interactive tasks in one flow can be parked on
 * their own prompts at the same time. Every pending request has to stay on
 * screen and stay independently answerable.
 */
describe("FlowDrawer agent inputs", () => {
  afterEach(cleanup);

  const two: AgentInputRequest[] = [
    { flowId: "f1", requestId: "r-1", prompt: "which colour?", taskName: "ask_colour" },
    { flowId: "f1", requestId: "r-2", prompt: "which size?", taskName: "ask_size" },
  ];

  const drawer = (
    agentInputs: AgentInputRequest[],
    onAnswerAgentInput?: (request: AgentInputRequest, answer: string) => void,
  ) => (
    <FlowDrawer
      open
      onClose={() => {}}
      title="flow"
      agentInputs={agentInputs}
      onAnswerAgentInput={onAnswerAgentInput}
    />
  );

  it("renders every pending request", () => {
    render(drawer(two));
    expect(screen.getAllByTestId("agent-input")).toHaveLength(2);
    expect(screen.getByText("which colour?")).toBeTruthy();
    expect(screen.getByText("which size?")).toBeTruthy();
  });

  it("sends each answer with its own request id", () => {
    const onAnswer = vi.fn();
    render(drawer(two, onAnswer));
    const [first, second] = screen.getAllByTestId("agent-input");

    fireEvent.change(within(first).getByTestId("agent-input-field"), {
      target: { value: "blue" },
    });
    fireEvent.click(within(first).getByTestId("agent-input-submit"));
    expect(onAnswer).toHaveBeenCalledWith(two[0], "blue");

    fireEvent.change(within(second).getByTestId("agent-input-field"), {
      target: { value: "large" },
    });
    fireEvent.click(within(second).getByTestId("agent-input-submit"));
    expect(onAnswer).toHaveBeenCalledWith(two[1], "large");
  });

  it("hands back the asking flow's id, not the drawer's own run", () => {
    // A nested conduit's interactive task prompts under the child flow id. The
    // answer has to be addressed to that id or the broker has no future to
    // resolve, so the drawer passes the request through rather than a bare id.
    const child: AgentInputRequest = {
      flowId: "f1-child",
      requestId: "r-9",
      prompt: "child asks?",
      taskName: "nested",
    };
    const onAnswer = vi.fn();
    render(drawer([child], onAnswer));

    fireEvent.change(screen.getByTestId("agent-input-field"), {
      target: { value: "yes" },
    });
    fireEvent.click(screen.getByTestId("agent-input-submit"));
    expect(onAnswer).toHaveBeenCalledWith(
      expect.objectContaining({ flowId: "f1-child", requestId: "r-9" }),
      "yes",
    );
  });

  it("leaves the other request answerable once one is removed", () => {
    const onAnswer = vi.fn();
    const { rerender } = render(drawer(two, onAnswer));
    // The reducer drops only the answered request; the drawer re-renders with
    // what is left.
    rerender(drawer([two[1]], onAnswer));

    expect(screen.getAllByTestId("agent-input")).toHaveLength(1);
    expect(screen.queryByText("which colour?")).toBeNull();

    fireEvent.change(screen.getByTestId("agent-input-field"), {
      target: { value: "large" },
    });
    fireEvent.click(screen.getByTestId("agent-input-submit"));
    expect(onAnswer).toHaveBeenCalledWith(two[1], "large");
  });

  it("renders no reply box when nothing is pending", () => {
    render(drawer([]));
    expect(screen.queryByTestId("agent-input")).toBeNull();
  });
});
