import { Layout } from "@/components/Layout";
import { Outlet, createRootRoute } from "@tanstack/react-router";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return (
    <Layout>
      <Outlet />
    </Layout>
  );
}
