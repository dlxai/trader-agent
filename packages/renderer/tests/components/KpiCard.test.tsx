import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { KpiCard } from "../../src/components/KpiCard.js";

describe("KpiCard", () => {
  it("renders label, value, and subtitle", () => {
    render(
      <KpiCard label="Equity" value="$10,127.50" subtitle="+$127.50 today" subtitleColor="green" />
    );
    expect(screen.getByText("Equity")).toBeDefined();
    expect(screen.getByText("$10,127.50")).toBeDefined();
    expect(screen.getByText("+$127.50 today")).toBeDefined();
  });

  it("works without subtitle", () => {
    render(<KpiCard label="Test" value="42" />);
    expect(screen.getByText("Test")).toBeDefined();
    expect(screen.getByText("42")).toBeDefined();
  });
});
