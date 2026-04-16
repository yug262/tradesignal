import { PlaceholderPage } from "@/pages/PlaceholderPage";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/mode-analysis")({
  component: () => (
    <PlaceholderPage
      title="Mode Analysis"
      description="Side-by-side outputs for all four analysis modes — Technical, Fundamental, Event-Based, and Hybrid God Mode — for any symbol or event candidate."
      phase={3}
      icon="BarChart3"
    />
  ),
});
