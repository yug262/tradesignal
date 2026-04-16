import { createActor } from "@/backend";
import type { Backend } from "@/backend";
import { useActor } from "@caffeineai/core-infrastructure";

/**
 * Base hook wrapping the backend actor.
 * Returns the typed actor instance and loading state.
 * All API hooks should build on top of this.
 */
export function useBackend() {
  const { actor, isFetching } = useActor<Backend>(createActor);
  return {
    actor,
    isActorReady: !!actor && !isFetching,
    isFetching,
  };
}
