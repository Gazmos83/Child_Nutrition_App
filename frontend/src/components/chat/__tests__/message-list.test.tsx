import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { emptyAssistantMessage, type ChatMessage } from "@/lib/chat-reducer";
import { CHAT_EMPTY, JUMP_TO_LATEST } from "@/lib/copy";
import { MessageList } from "../message-list";

const MESSAGES: ChatMessage[] = [
  { id: "u1", role: "user", text: "What can I feed at 8 months?" },
  { ...emptyAssistantMessage("a1"), text: "Soft foods are a great start", status: "done" },
];

function renderList() {
  return render(<MessageList messages={MESSAGES} onRetry={() => {}} retryDisabled={false} />);
}

function scrollTo(el: HTMLElement, { top, height, client }: { top: number; height: number; client: number }) {
  Object.defineProperty(el, "scrollHeight", { value: height, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: client, configurable: true });
  el.scrollTop = top;
  fireEvent.scroll(el);
}

describe("MessageList", () => {
  it("shows the invitation when there are no messages", () => {
    render(<MessageList messages={[]} onRetry={() => {}} retryDisabled={false} />);
    expect(screen.getByText(CHAT_EMPTY)).toBeInTheDocument();
  });

  it("stays pinned to the bottom by default, with no jump button", () => {
    renderList();
    expect(screen.queryByRole("button", { name: JUMP_TO_LATEST })).toBeNull();
  });

  it("offers a jump back down once the parent scrolls up, and honours it", () => {
    const { container } = renderList();
    const scroller = container.firstElementChild as HTMLElement;
    scrollTo(scroller, { top: 100, height: 1000, client: 400 });
    const jump = screen.getByRole("button", { name: JUMP_TO_LATEST });
    fireEvent.click(jump);
    expect(screen.queryByRole("button", { name: JUMP_TO_LATEST })).toBeNull();
  });

  it("keeps the view unpinned while reading near the top", () => {
    const { container } = renderList();
    const scroller = container.firstElementChild as HTMLElement;
    scrollTo(scroller, { top: 0, height: 1000, client: 400 });
    expect(screen.getByRole("button", { name: JUMP_TO_LATEST })).toBeInTheDocument();
    // Back near the bottom, the button leaves on its own.
    scrollTo(scroller, { top: 590, height: 1000, client: 400 });
    expect(screen.queryByRole("button", { name: JUMP_TO_LATEST })).toBeNull();
  });
});
