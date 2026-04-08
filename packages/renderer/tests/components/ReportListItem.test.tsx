import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { ReportListItem } from "../../src/components/ReportListItem.js";

describe("ReportListItem", () => {
  it("renders date, period, trade count, and positive pnl", () => {
    render(
      <ReportListItem
        date="Apr 6, 2026"
        period="weekly"
        tradeCount={24}
        netPnl={127.5}
        isSelected={false}
        onClick={() => {}}
      />,
    );
    expect(screen.getByText("Apr 6, 2026")).toBeDefined();
    expect(screen.getByText(/Weekly · 24 trades · \+\$127\.50/)).toBeDefined();
  });

  it("renders negative pnl with minus sign", () => {
    render(
      <ReportListItem
        date="Apr 4, 2026"
        period="daily"
        tradeCount={3}
        netPnl={-8.4}
        isSelected={false}
        onClick={() => {}}
      />,
    );
    expect(screen.getByText(/Daily · 3 trades · -\$8\.40/)).toBeDefined();
  });

  it("calls onClick when clicked", () => {
    const handleClick = vi.fn();
    render(
      <ReportListItem
        date="Apr 6, 2026"
        period="weekly"
        tradeCount={24}
        netPnl={127.5}
        isSelected={false}
        onClick={handleClick}
      />,
    );
    fireEvent.click(screen.getByText("Apr 6, 2026"));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});
