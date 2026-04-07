import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

function Hello() {
  return <span>hello</span>;
}

describe("@pmt/renderer smoke", () => {
  it("renders a React component", () => {
    render(<Hello />);
    expect(screen.getByText("hello")).toBeDefined();
  });
});
