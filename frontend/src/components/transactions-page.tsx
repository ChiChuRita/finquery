import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import type { RowSelectionState } from '@tanstack/react-table'
import { PlusIcon, SearchIcon, TableIcon, XIcon } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { DateRangePicker } from '@/components/date-range-picker'
import { PageBar } from '@/components/page'
import { TransactionsTable, type Patch } from '@/components/transactions-table'
import {
  AddTransactionDialog,
  ConfirmDeleteDialog,
  ConfirmRecategorizeDialog,
} from '@/components/transaction-dialogs'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import {
  accountsQuery,
  bulkDelete,
  bulkRecategorize,
  categoriesQuery,
  hasFilters,
  NO_FILTERS,
  patchTransaction,
  transactionsQuery,
  type AccountRef,
  type CategoryRef,
  type Filters,
  type Transaction,
  type TransactionPage,
} from '@/lib/api'
import { formatEur } from '@/lib/format'
import { useWorkspace } from '@/lib/workspace'

const ALL = '__all__'
/** The bulk bar starts on nothing chosen. Its select used to default to Needs review, which is
 *  one stray click away from taking the category off every selected row, and three rows lost
 *  theirs that way in the e2e of 2026-09-05 (p2). */
const NOTHING_CHOSEN = ''
const NO_ROWS: Transaction[] = []
const NO_CATEGORIES: CategoryRef[] = []
const NO_ACCOUNTS: AccountRef[] = []

/** Rewrite one row wherever it sits in the loaded pages, for the optimistic edit and its answer. */
function withRow(
  data: InfiniteData<TransactionPage> | undefined,
  id: string,
  next: (row: Transaction) => Transaction,
): InfiniteData<TransactionPage> | undefined {
  if (!data) return data
  return {
    ...data,
    pages: data.pages.map((page) => ({
      ...page,
      rows: page.rows.map((row) => (row.id === id ? next(row) : row)),
    })),
  }
}

function FilterBar({
  filters,
  categories,
  accounts,
  onChange,
}: {
  filters: Filters
  categories: CategoryRef[]
  accounts: AccountRef[]
  onChange: (next: Filters) => void
}) {
  // The text filter runs on the server, so it waits for a pause in the typing.
  const [text, setText] = useState(filters.q)
  // What this bar last sent up. The bar is not the only place the filters are cleared from
  // (the empty state offers it too), and without this the debounce would push the old text
  // straight back in.
  const pushed = useRef(filters.q)
  useEffect(() => {
    if (filters.q === pushed.current) return
    pushed.current = filters.q
    setText(filters.q)
  }, [filters.q])
  useEffect(() => {
    if (text === filters.q) return
    const timer = setTimeout(() => {
      pushed.current = text
      onChange({ ...filters, q: text })
    }, 250)
    return () => clearTimeout(timer)
  }, [text, filters, onChange])

  const set = (fields: Partial<Filters>) => onChange({ ...filters, ...fields })

  return (
    <div className="flex flex-wrap items-center gap-3 border-b px-6 py-3">
      {/* The search box is the one control that gives way: it lays out at w-44, so Clear still
          fits on the row at 1440 with every filter set, grows back to w-56 when there is room,
          and never shrinks below w-44 (at 1024 the bar wraps instead). */}
      <InputGroup className="w-44 max-w-56 shrink-0 grow">
        <InputGroupInput
          aria-label="Search descriptions and counterparties"
          onChange={(event) => setText(event.target.value)}
          placeholder="Search text"
          value={text}
        />
        <InputGroupAddon>
          <SearchIcon aria-hidden="true" />
        </InputGroupAddon>
      </InputGroup>

      <DateRangePicker
        from={filters.date_from}
        onChange={(range) => set({ date_from: range.from, date_to: range.to })}
        to={filters.date_to}
      />

      <Select
        onValueChange={(value) => set({ category_id: value === ALL ? '' : value })}
        value={filters.category_id || ALL}
      >
        <SelectTrigger aria-label="Filter by category" className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="max-h-72">
          <SelectItem value={ALL}>Every category</SelectItem>
          <SelectSeparator />
          {categories.map((category) => (
            <SelectItem key={category.id} value={category.id}>
              {category.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        onValueChange={(value) => set({ account_id: value === ALL ? '' : value })}
        value={filters.account_id || ALL}
      >
        <SelectTrigger aria-label="Filter by account" className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Every account</SelectItem>
          <SelectSeparator />
          {accounts.map((account) => (
            <SelectItem key={account.id} value={account.id}>
              {account.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Label className="flex h-8 cursor-pointer items-center gap-2 rounded-lg border px-2.5 text-sm">
        <Checkbox
          checked={filters.needs_review}
          onCheckedChange={(checked) => set({ needs_review: checked === true })}
        />
        Needs review
      </Label>

      {hasFilters(filters) && (
        <Button
          onClick={() => {
            setText('')
            onChange(NO_FILTERS)
          }}
          size="sm"
          variant="ghost"
        >
          <XIcon /> Clear
        </Button>
      )}
    </div>
  )
}

export function TransactionsPage() {
  const { profile } = useWorkspace()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [selection, setSelection] = useState<RowSelectionState>({})
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [target, setTarget] = useState(NOTHING_CHOSEN)

  // Everything on this page is read for the profile the sidebar is showing.
  const list = useInfiniteQuery(transactionsQuery(profile?.id, filters))
  const { data: categories = NO_CATEGORIES } = useQuery(categoriesQuery(profile?.id))
  const { data: accounts = NO_ACCOUNTS } = useQuery(accountsQuery(profile?.id))

  const rows = useMemo(() => list.data?.pages.flatMap((page) => page.rows) ?? NO_ROWS, [list.data])
  const total = list.data?.pages[0]?.total ?? 0
  const selectedIds = useMemo(() => Object.keys(selection).filter((id) => selection[id]), [selection])

  const refresh = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['transactions'] }),
    [queryClient],
  )

  // The row shows the new value at once; a refusal puts the old pages back and the cell says why.
  // Stable, because the table's columns close over it and rebuilding them on every render would
  // hand `useTable` new options forever.
  const patch = useCallback<Patch>(
    async (row, edit, optimistic) => {
      if (!profile) throw new Error('No profile is active yet.')
      const key = transactionsQuery(profile.id, filters).queryKey
      const previous = queryClient.getQueryData<InfiniteData<TransactionPage>>(key)
      queryClient.setQueryData(key, withRow(previous, row.id, (current) => ({ ...current, ...optimistic })))
      try {
        const saved = await patchTransaction(profile.id, row.id, edit)
        queryClient.setQueryData<InfiniteData<TransactionPage>>(key, (data) => withRow(data, saved.id, () => saved))
      } catch (failure) {
        if (previous) queryClient.setQueryData(key, previous)
        throw failure
      }
    },
    [filters, profile, queryClient],
  )

  const reload = useCallback(() => void refresh(), [refresh])
  const { fetchNextPage, hasNextPage, isFetchingNextPage } = list
  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage()
  }, [fetchNextPage, hasNextPage, isFetchingNextPage])

  const recategorize = useMutation({
    // A bulk move sets the category and leaves no subcategory, the same as one cell would.
    mutationFn: () => {
      if (!profile) throw new Error('No profile is active yet.')
      return bulkRecategorize(profile.id, selectedIds, target === ALL ? null : target, null)
    },
    onSuccess: async () => {
      setSelection({})
      setTarget(NOTHING_CHOSEN)
      await refresh()
    },
  })
  const targetName =
    target === ALL ? 'Needs review' : (categories.find((category) => category.id === target)?.name ?? '')

  const remove = useMutation({
    mutationFn: () => {
      if (!profile) throw new Error('No profile is active yet.')
      return bulkDelete(profile.id, selectedIds)
    },
    onSuccess: async () => {
      setSelection({})
      setExpandedId(null)
      await refresh()
    },
  })

  const failure = list.error ?? recategorize.error ?? remove.error

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageBar title="Transactions">
        <p className="truncate text-muted-foreground text-xs">
          {list.isPending
            ? 'Loading...'
            : `${total} ${total === 1 ? 'row' : 'rows'}${
                hasFilters(filters)
                  ? total === 1
                    ? ' matches these filters'
                    : ' match these filters'
                  : ' in this profile'
              }`}
          {rows.length < total && ` · ${rows.length} loaded`}
        </p>
        <div className="ml-auto flex items-center gap-2">
          {list.isFetching && !list.isPending && <Spinner className="size-3.5 text-muted-foreground" />}
          <AddTransactionDialog accounts={accounts} categories={categories} onCreated={reload} />
        </div>
      </PageBar>

      <FilterBar accounts={accounts} categories={categories} filters={filters} onChange={setFilters} />

      {failure && (
        <p className="border-b bg-destructive/5 px-6 py-2 text-destructive text-sm" role="alert">
          {failure.message}
        </p>
      )}

      {total === 0 && !list.isPending ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              {hasFilters(filters) ? <SearchIcon aria-hidden="true" /> : <TableIcon aria-hidden="true" />}
            </EmptyMedia>
            <EmptyTitle>
              {hasFilters(filters) ? 'No transaction matches these filters.' : 'This profile has no transactions yet.'}
            </EmptyTitle>
            <EmptyDescription>
              {hasFilters(filters)
                ? 'Try fewer of them, or start again from every booking.'
                : accounts.length > 0
                  ? 'Drop a bank statement into the chat, or add a booking by hand.'
                  : 'Drop a bank statement into the chat. Manual rows need an account to book against.'}
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            {hasFilters(filters) ? (
              <Button onClick={() => setFilters(NO_FILTERS)} size="sm" variant="outline">
                <XIcon data-icon="inline-start" />
                Clear the filters
              </Button>
            ) : (
              // Every import happens in a chat, so the way out of an empty table is a chat.
              <Button asChild size="sm" variant="outline">
                <Link to="/">
                  <PlusIcon data-icon="inline-start" />
                  New chat
                </Link>
              </Button>
            )}
          </EmptyContent>
        </Empty>
      ) : (
        <TransactionsTable
          accounts={accounts}
          categories={categories}
          expandedId={expandedId}
          onExpand={setExpandedId}
          onPatch={patch}
          onReachEnd={loadMore}
          onSelectionChange={setSelection}
          onSplitChanged={reload}
          rows={rows}
          selection={selection}
          total={total}
        />
      )}

      {selectedIds.length > 0 && (
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-t bg-card px-6 py-3">
          <span className="font-medium text-sm">
            {selectedIds.length} selected
            <span className="pl-2 font-normal text-muted-foreground text-xs tabular-nums">
              {formatEur(
                rows
                  .filter((row) => selection[row.id])
                  .reduce((sum, row) => sum + row.amount_cents, 0),
              )}
            </span>
          </span>

          <div className="flex items-center gap-2">
            <Select onValueChange={setTarget} value={target}>
              <SelectTrigger aria-label="Category to move them to" className="w-56" size="sm">
                <SelectValue placeholder="Move them to..." />
              </SelectTrigger>
              {/* Anchored to the trigger rather than to the chosen item, because the bar it
                  hangs off sits at the bottom of the window. Categories only: the subcategory
                  of a row is a detail its own cell edits. */}
              <SelectContent className="max-h-96" position="popper">
                <SelectItem value={ALL}>Needs review</SelectItem>
                <SelectSeparator />
                {categories.map((category) => (
                  <SelectItem key={category.id} value={category.id}>
                    {category.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {/* No target, no button: a grey Recategorize next to a live Delete reads as broken.
                The select above is the step that makes it appear. */}
            {target !== NOTHING_CHOSEN && (
              <ConfirmRecategorizeDialog
                count={selectedIds.length}
                disabled={false}
                onConfirm={() => recategorize.mutateAsync()}
                pending={recategorize.isPending}
                target={targetName}
              />
            )}
          </div>

          <ConfirmDeleteDialog
            count={selectedIds.length}
            onConfirm={() => remove.mutateAsync()}
            pending={remove.isPending}
          />

          <Button className="ml-auto" onClick={() => setSelection({})} size="sm" variant="ghost">
            Clear the selection
          </Button>
        </div>
      )}
    </div>
  )
}
