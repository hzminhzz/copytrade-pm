import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import OpsDashboard from "./ops-dashboard";
import "./globals.css";

const root = document.getElementById("root");
if (!root) throw new Error("Dashboard mount node missing");
createRoot(root).render(<StrictMode><OpsDashboard userName="Operator" /></StrictMode>);
