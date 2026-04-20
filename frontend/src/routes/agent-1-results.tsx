import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/agent-1-results')({
  component: RouteComponent,
})

function RouteComponent() {
  return <div>Hello "/agent-1-results"!</div>
}
