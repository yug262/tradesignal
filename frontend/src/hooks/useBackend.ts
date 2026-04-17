/**
 * useBackend hook — simplified for REST.
 * No longer needs an ICP actor. Always "ready" since we just call fetch.
 */
export function useBackend() {
  return {
    isActorReady: true,
    isFetching: false,
  };
}
