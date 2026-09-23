import { useContext } from 'react'
import { useQuery } from '@tanstack/react-query'

import { WorkspaceContext } from '@/contexts/workspace-context'
import { timezones as timezonesApi } from '@/lib/api'

/**
 * The timezones a signed-in person can pick from, plus the application
 * default a workspace follows when it has none of its own. Cached for the
 * session: the list never changes and the default rarely does.
 */
export function useTimezones() {
  return useQuery({
    queryKey: ['timezones'],
    queryFn: timezonesApi.list,
    staleTime: Infinity,
  })
}

/**
 * The timezone the server keeps the active workspace's books in, or undefined
 * while that is still unknown. Read through the context object directly so a
 * component rendered outside a WorkspaceProvider (previews, tests) degrades to
 * "unknown" instead of throwing.
 */
export function useEffectiveTimezone(): string | undefined {
  const workspace = useContext(WorkspaceContext)
  const { data } = useTimezones()
  return workspace?.current?.timezone ?? data?.default ?? undefined
}
