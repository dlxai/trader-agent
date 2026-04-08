import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";
import { useSettings } from "../src/stores/settings.js";
import { usePortfolio } from "../src/stores/portfolio.js";
import { usePositions } from "../src/stores/positions.js";
import { useCoordinator } from "../src/stores/coordinator.js";
import { useChat } from "../src/stores/chat.js";

// Capture each store's pristine initial state once at module load, before any
// test has a chance to mutate it, so we can restore it between tests.
const initialSettings = useSettings.getState();
const initialPortfolio = usePortfolio.getState();
const initialPositions = usePositions.getState();
const initialCoordinator = useCoordinator.getState();
const initialChat = useChat.getState();

beforeEach(() => {
  useSettings.setState(initialSettings, true);
  usePortfolio.setState(initialPortfolio, true);
  usePositions.setState(initialPositions, true);
  useCoordinator.setState(initialCoordinator, true);
  useChat.setState(initialChat, true);
});

afterEach(() => {
  cleanup();
});
