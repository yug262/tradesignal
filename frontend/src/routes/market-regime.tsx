import { PlaceholderPage } from "@/pages/PlaceholderPage";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/market-regime")({
  component: () => (
    <PlaceholderPage
      title="Market Regime"
      description="Index and sector state analysis, trend classification, volatility regime tracking, and historical regime transitions with visual timeline."
      phase={2}
      icon="Globe"
    />
  ),
});
