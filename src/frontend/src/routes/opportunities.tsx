import { PlaceholderPage } from "@/pages/PlaceholderPage";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/opportunities")({
  component: () => (
    <PlaceholderPage
      title="Live Trade Opportunities"
      description="Real-time filterable list of all tradeable opportunities with detailed trade cards, entry/exit levels, risk-reward ratios, and confidence scores."
      phase={2}
      icon="TrendingUp"
    />
  ),
});
