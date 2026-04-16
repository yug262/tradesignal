import { PlaceholderPage } from "@/pages/PlaceholderPage";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/symbols/$symbolId")({
  component: SymbolDetailPage,
});

function SymbolDetailPage() {
  const { symbolId } = Route.useParams();
  return (
    <PlaceholderPage
      title={`Symbol Detail: ${symbolId}`}
      description="Deep-dive view for any stock — news timeline, price chart, multi-mode analysis, trade ideas, and full decision history."
      phase={5}
      icon="Activity"
    />
  );
}
