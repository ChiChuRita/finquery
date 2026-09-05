import { useQuery } from '@tanstack/react-query'

import { MODEL_SLOTS, modelsQuery, type ModelSlot } from '@/lib/api'

/** What to call a slot: the display name of the model that fills it on the running provider.
 *
 * `GET /api/models` names the models the server really resolves the two slots to, hosted or
 * local, so the selector, the turn chips and the models card all say the same thing and never
 * name a model that is not running. Until that answer arrives the local names stand in. */
export function useSlotLabel(): (slot: ModelSlot | undefined) => string | undefined {
  const { data } = useQuery(modelsQuery)
  return (slot) =>
    data?.models.find((model) => model.slot === slot)?.label ?? MODEL_SLOTS.find((m) => m.slot === slot)?.label
}
