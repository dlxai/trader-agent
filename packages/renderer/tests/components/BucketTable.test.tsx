import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import {
  BucketTable,
  type BucketRow,
} from "../../src/components/BucketTable.js";

const MOCK_ROWS: BucketRow[] = [
  { bucket: 0.4, trades: 7, wins: 5, winRate: 0.714, netPnl: 56.2 },
  { bucket: 0.5, trades: 4, wins: 2, winRate: 0.5, netPnl: -12.3 },
];

describe("BucketTable", () => {
  it("renders all column headers", () => {
    render(<BucketTable rows={MOCK_ROWS} />);
    expect(screen.getByText("Bucket")).toBeDefined();
    expect(screen.getByText("Trades")).toBeDefined();
    expect(screen.getByText("Wins")).toBeDefined();
    expect(screen.getByText("Win rate")).toBeDefined();
    expect(screen.getByText("Net PnL")).toBeDefined();
  });

  it("renders one row per bucket with formatted values", () => {
    render(<BucketTable rows={MOCK_ROWS} />);
    expect(screen.getByText("0.40")).toBeDefined();
    expect(screen.getByText("0.50")).toBeDefined();
    expect(screen.getByText("71.4%")).toBeDefined();
    expect(screen.getByText("50.0%")).toBeDefined();
    expect(screen.getByText("+$56.20")).toBeDefined();
    expect(screen.getByText("-$12.30")).toBeDefined();
  });

  it("renders an empty state when there are no rows", () => {
    render(<BucketTable rows={[]} />);
    expect(screen.getByText(/No bucket data for this report/)).toBeDefined();
  });
});
