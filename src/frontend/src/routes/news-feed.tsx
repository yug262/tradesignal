import { NewsFeedPage } from "@/pages/NewsFeedPage";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/news-feed")({
  component: NewsFeedPage,
});
