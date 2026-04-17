import { createFileRoute } from '@tanstack/react-router'
import { GroupingPage } from '../pages/GroupingPage'

export const Route = createFileRoute('/grouping')({
  component: GroupingPage,
})
