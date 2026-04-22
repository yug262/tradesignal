import { createFileRoute } from "@tanstack/react-router";
import { PaperTradingPage } from "@/pages/PaperTradingPage";

export const Route = createFileRoute("/paper-trading")({
  component: PaperTradingPage,
});
