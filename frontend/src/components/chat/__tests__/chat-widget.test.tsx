import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { emptyAssistantMessage } from "@/lib/chat-reducer";
import { APP_TITLE, CHAT_CLOSE_LABEL, CHAT_OPEN_LABEL } from "@/lib/copy";
import { ChatWidget } from "../chat-widget";

// The launcher artwork is a static import; next/image needs real dimensions, jsdom has none.
vi.mock("next/image", () => ({
  default: ({ alt, ...props }: Record<string, unknown> & { alt?: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...props} src="chef.png" alt={alt ?? ""} />
  ),
}));

const CHAT = {
  messages: [
    { id: "u1", role: "user" as const, text: "How much iron at 8 months?" },
    { ...emptyAssistantMessage("a1"), text: "Around 11 mg a day", status: "done" as const },
  ],
  send: vi.fn(),
  retry: vi.fn(),
  isPending: false,
};

function launcher(): HTMLElement {
  return screen.getByTestId("chat-launcher");
}

function panel(): HTMLElement {
  return screen.getByTestId("chat-panel");
}

describe("ChatWidget", () => {
  it("starts closed, with an inviting launcher", () => {
    render(<ChatWidget chat={CHAT} feedNotice={null} />);
    expect(launcher()).toHaveAttribute("aria-expanded", "false");
    expect(launcher()).toHaveAccessibleName(CHAT_OPEN_LABEL);
    expect(panel().className).toContain("invisible");
  });

  it("opens on the launcher, titled and populated", () => {
    render(<ChatWidget chat={CHAT} feedNotice={null} />);
    fireEvent.click(launcher());
    expect(launcher()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog", { name: APP_TITLE })).toBe(panel());
    expect(panel().className).not.toContain("invisible");
    expect(screen.getByText("Around 11 mg a day")).toBeInTheDocument();
  });

  it("keeps the conversation and the draft through close and reopen", () => {
    render(<ChatWidget chat={CHAT} feedNotice={null} />);
    fireEvent.click(launcher());
    const draft = screen.getByRole("textbox");
    fireEvent.change(draft, { target: { value: "and vitamin D?" } });
    fireEvent.click(within(panel()).getByRole("button", { name: CHAT_CLOSE_LABEL }));
    expect(panel().className).toContain("invisible");
    fireEvent.click(launcher());
    expect(screen.getByText("Around 11 mg a day")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("and vitamin D?");
  });

  it("closes on Escape and hands focus back to the launcher", () => {
    render(<ChatWidget chat={CHAT} feedNotice={null} />);
    fireEvent.click(launcher());
    fireEvent.keyDown(panel(), { key: "Escape" });
    expect(panel().className).toContain("invisible");
    expect(launcher()).toHaveFocus();
  });

  it("shows a feed notice inside the panel", () => {
    render(<ChatWidget chat={CHAT} feedNotice="A note about a feed" />);
    fireEvent.click(launcher());
    expect(screen.getByTestId("feed-notice")).toHaveTextContent("A note about a feed");
  });
});
