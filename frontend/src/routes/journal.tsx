import { PlaceholderPage } from "@/pages/PlaceholderPage";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/journal")({
  component: () => (
    <PlaceholderPage
      title="Journal / History"
      description="Searchable, filterable history of all system outputs, trade outcomes, performance metrics, win rates, and decision explainability logs."
      phase={6}
      icon="BookOpen"
    />
  ),
});
