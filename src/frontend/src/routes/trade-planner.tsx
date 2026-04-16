import { PlaceholderPage } from "@/pages/PlaceholderPage";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/trade-planner")({
  component: () => (
    <PlaceholderPage
      title="Trade Planner"
      description="Detailed trade plan builder with full rationale, position sizing, risk-reward validation, entry/stop/target levels, and change history tracking."
      phase={4}
      icon="ClipboardList"
    />
  ),
});
