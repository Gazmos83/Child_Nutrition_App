import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerText } from "../answer-text";

describe("AnswerText", () => {
  it("anchors [n] markers to the message's sources", () => {
    render(<AnswerText text="Iron matters early [1][2]." messageId="m1" />);
    const first = screen.getByRole("link", { name: "Source 1" });
    const second = screen.getByRole("link", { name: "Source 2" });
    expect(first).toHaveAttribute("href", "#src-m1-1");
    expect(second).toHaveAttribute("href", "#src-m1-2");
  });

  it("anchors a marker inside a list item", () => {
    const { container } = render(<AnswerText text={"Good options:\n- oatmeal [2]"} messageId="m1" />);
    const item = container.querySelector("ul li");
    expect(item).not.toBeNull();
    expect(item).toHaveTextContent("oatmeal [2]");
    expect(item!.querySelector('a[href="#src-m1-2"]')).not.toBeNull();
  });

  it("anchors a marker inside bold text", () => {
    const { container } = render(<AnswerText text="This is **key [3]** advice" messageId="m9" />);
    const bold = container.querySelector("strong");
    expect(bold).not.toBeNull();
    expect(bold!.querySelector('a[href="#src-m9-3"]')).not.toBeNull();
  });

  it("renders bulleted lines as a real list and numbered lines in order", () => {
    const text = "Try these:\n- oatmeal\n- lentils\n\n1. wash\n2. mash";
    const { container } = render(<AnswerText text={text} messageId="m1" />);
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelector("p")).toHaveTextContent("Try these:");
  });

  it("keeps half-streamed markup as plain text", () => {
    render(<AnswerText text="This is **bold" messageId="m1" />);
    expect(screen.getByText("This is **bold")).toBeInTheDocument();
  });
});
