import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { PositionTable, type Position } from "../../src/components/PositionTable.js";

const samplePositions: Position[] = [
  {
    signalId: "s1",
    marketTitle: "Trump approval > 50%",
    side: "buy_yes",
    entryPrice: 0.452,
    currentPrice: 0.481,
    sizeUsdc: 125,
    pnl: 8.02,
    heldDuration: "42m",
  },
  {
    signalId: "s2",
    marketTitle: "BTC > $100k",
    side: "buy_yes",
    entryPrice: 0.520,
    currentPrice: 0.508,
    sizeUsdc: 108,
    pnl: -2.49,
    heldDuration: "1h 18m",
  },
];

describe("PositionTable", () => {
  it("renders all positions with market titles", () => {
    render(<PositionTable positions={samplePositions} />);
    expect(screen.getByText("Trump approval > 50%")).toBeDefined();
    expect(screen.getByText("BTC > $100k")).toBeDefined();
  });

  it("shows PnL with appropriate sign", () => {
    render(<PositionTable positions={samplePositions} />);
    expect(screen.getByText(/\+\$8\.02/)).toBeDefined();
    expect(screen.getByText(/-\$2\.49/)).toBeDefined();
  });

  it("renders empty state when no positions", () => {
    render(<PositionTable positions={[]} />);
    expect(screen.getByText(/no open positions/i)).toBeDefined();
  });
});
