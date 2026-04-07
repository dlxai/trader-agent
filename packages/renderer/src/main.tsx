import React from "react";
import { createRoot } from "react-dom/client";

function App() {
  return <div>Polymarket Trader — placeholder, real UI in M4</div>;
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<App />);
}

export const PACKAGE_NAME = "@pmt/renderer";
