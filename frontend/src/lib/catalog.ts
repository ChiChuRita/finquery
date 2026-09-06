import { useQuery } from '@tanstack/react-query'

import { modelsQuery, type CatalogEntry, type ModelKey } from '@/lib/api'

/** The model catalog as the browser sees it: the four entries, plus the two fast slots.
 *
 * `GET /api/models` is the only place a model name comes from, so the picker, the turn chips,
 * the History and the models card all say the same thing and none of them can name a model the
 * server does not offer. Before that answer arrives the list is empty and `label` falls back to
 * the key, which is readable enough for the half second it lasts. */
export function useCatalog(): {
  entries: CatalogEntry[]
  defaultKey: ModelKey | undefined
  entry: (key: ModelKey | undefined) => CatalogEntry | undefined
  label: (key: ModelKey | undefined) => string | undefined
} {
  const { data } = useQuery(modelsQuery)
  const all = [...(data?.entries ?? []), ...(data?.fast_slots ?? [])]
  const entry = (key: ModelKey | undefined) => all.find((candidate) => candidate.key === key)
  return {
    entries: data?.entries ?? [],
    defaultKey: data?.default_key,
    entry,
    label: (key) => (key === undefined ? undefined : (entry(key)?.label ?? key)),
  }
}

/** What one entry is called, for the screens that only need the name. */
export function useModelLabel(): (key: ModelKey | undefined) => string | undefined {
  return useCatalog().label
}
