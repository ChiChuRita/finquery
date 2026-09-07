import {
  createColumnHelper,
  rowSelectionFeature,
  tableFeatures,
  useTable,
  type RowSelectionState,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ChevronRightIcon, SplitIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { SplitEditor } from '@/components/split-editor'
import { AmountCell, DateCell, PickerCell, TextCell, type Choice } from '@/components/transaction-cells'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import type { AccountRef, CategoryRef, Transaction, TransactionEdit } from '@/lib/api'
import { cn } from '@/lib/utils'

/** What the row height is before a row has been measured. Expanded rows measure themselves. */
const ROW_HEIGHT = 36

const features = tableFeatures({
  rowSelectionFeature,
  // Each column carries its own share of the grid, so header and rows cannot drift apart.
  columnMeta: {} as { width: string },
})
const helper = createColumnHelper<typeof features, Transaction>()

export type Patch = (row: Transaction, edit: TransactionEdit, optimistic: Partial<Transaction>) => Promise<unknown>

export function TransactionsTable({
  rows,
  total,
  categories,
  accounts,
  selection,
  onSelectionChange,
  expandedId,
  onExpand,
  onPatch,
  onSplitChanged,
  onReachEnd,
}: {
  rows: Transaction[]
  total: number
  categories: CategoryRef[]
  accounts: AccountRef[]
  selection: RowSelectionState
  onSelectionChange: (next: RowSelectionState) => void
  expandedId: string | null
  onExpand: (id: string | null) => void
  onPatch: Patch
  onSplitChanged: () => void
  onReachEnd: () => void
}) {
  const scroller = useRef<HTMLDivElement>(null)

  const categoryChoices: Choice[] = useMemo(
    () => categories.map((category) => ({ id: category.id, name: category.name })),
    [categories],
  )
  const accountChoices: Choice[] = useMemo(
    () => accounts.map((account) => ({ id: account.id, name: account.name })),
    [accounts],
  )

  const columns = useMemo(
    () =>
      helper.columns([
        helper.display({
          id: 'select',
          meta: { width: '2.25rem' },
          // Every control in a row is 28px tall (h-7) and the row aligns to the top, so the error
          // line under an input can grow a cell. The checkbox is 16px: give it the same 28px box
          // or it sits above the middle of its row.
          header: ({ table }) => (
            <div className="flex h-7 items-center">
              <Checkbox
                aria-label="Select every loaded row"
                checked={table.getIsAllRowsSelected() || (table.getIsSomeRowsSelected() && 'indeterminate')}
                onCheckedChange={() => table.toggleAllRowsSelected()}
              />
            </div>
          ),
          cell: ({ row }) => (
            <div className="flex h-7 items-center">
              <Checkbox
                aria-label={`Select ${row.original.description}`}
                checked={row.getIsSelected()}
                onCheckedChange={() => row.toggleSelected()}
              />
            </div>
          ),
        }),
        helper.display({
          id: 'expand',
          meta: { width: '2rem' },
          header: () => <span className="sr-only">Splits</span>,
          cell: ({ row }) => {
            const open = expandedId === row.original.id
            return (
              <button
                aria-expanded={open}
                aria-label={open ? 'Hide the split' : 'Show the split'}
                className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-ring"
                onClick={() => onExpand(open ? null : row.original.id)}
                type="button"
              >
                <ChevronRightIcon className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
              </button>
            )
          },
        }),
        helper.accessor('booked_on', {
          id: 'booked_on',
          header: 'Date',
          meta: { width: '7rem' },
          cell: ({ row }) => (
            <DateCell
              onSave={(booked_on) => onPatch(row.original, { booked_on }, { booked_on })}
              value={row.original.booked_on}
            />
          ),
        }),
        helper.accessor('description', {
          id: 'description',
          header: 'Description',
          meta: { width: 'minmax(11rem, 1.6fr)' },
          cell: ({ row }) => (
            <div className="flex min-w-0 items-center gap-1.5">
              <div className="min-w-0 flex-1">
                <TextCell
                  label={`Description of ${row.original.description}`}
                  onSave={(description) => onPatch(row.original, { description }, { description })}
                  value={row.original.description}
                />
              </div>
              {row.original.split_count > 0 && (
                <Badge
                  className="shrink-0 cursor-default"
                  title={`Split into ${row.original.split_count} legs`}
                  variant="secondary"
                >
                  <SplitIcon /> {row.original.split_count}
                </Badge>
              )}
            </div>
          ),
        }),
        helper.accessor('title', {
          id: 'title',
          // The one column of this table that is not edited here: it is written by the
          // enrichment step, and a cell that refuses a click has to say why.
          header: () => (
            <span title="Written by the enrichment step at import, not edited here. Change the description instead.">
              Enriched title
            </span>
          ),
          meta: { width: 'minmax(8.5rem, 0.8fr)' },
          cell: ({ row }) => (
            <span className="block truncate px-1.5 py-1 text-muted-foreground text-sm" title={row.original.title ?? ''}>
              {row.original.title ?? '–'}
            </span>
          ),
        }),
        helper.accessor('amount_cents', {
          id: 'amount_cents',
          header: () => <span className="block text-right">Amount</span>,
          meta: { width: '7.5rem' },
          cell: ({ row }) => (
            <AmountCell
              cents={row.original.amount_cents}
              onSave={(amount_cents) => onPatch(row.original, { amount_cents }, { amount_cents })}
            />
          ),
        }),
        helper.accessor('category', {
          id: 'category',
          header: 'Category',
          meta: { width: 'minmax(8.5rem, 1fr)' },
          cell: ({ row }) => (
            <PickerCell
              choices={categoryChoices}
              label={`Category of ${row.original.description}`}
              onSave={(category_id) =>
                onPatch(
                  row.original,
                  { category_id },
                  {
                    category_id,
                    category: categoryChoices.find((choice) => choice.id === category_id)?.name ?? null,
                    // A category change drops a subcategory that belonged to the old one.
                    subcategory_id: null,
                    subcategory: null,
                  },
                )
              }
              placeholder="Needs review"
              value={row.original.category_id}
            />
          ),
        }),
        helper.accessor('subcategory', {
          id: 'subcategory',
          header: 'Subcategory',
          meta: { width: 'minmax(7rem, 1fr)' },
          cell: ({ row }) => {
            const owner = categories.find((category) => category.id === row.original.category_id)
            if (!owner) {
              return <span className="block px-1.5 py-1 text-muted-foreground text-sm">–</span>
            }
            const choices = owner.subcategories.map((sub) => ({ id: sub.id, name: sub.name }))
            return (
              <PickerCell
                choices={choices}
                label={`Subcategory of ${row.original.description}`}
                onSave={(subcategory_id) =>
                  onPatch(
                    row.original,
                    { subcategory_id },
                    {
                      subcategory_id,
                      subcategory: choices.find((choice) => choice.id === subcategory_id)?.name ?? null,
                    },
                  )
                }
                clearLabel="No subcategory"
                placeholder="–"
                value={row.original.subcategory_id}
              />
            )
          },
        }),
        helper.accessor('account', {
          id: 'account',
          header: 'Account',
          meta: { width: 'minmax(11.5rem, 1fr)' },
          cell: ({ row }) => (
            <PickerCell
              choices={accountChoices}
              clearable={false}
              label={`Account of ${row.original.description}`}
              onSave={(account_id) =>
                account_id === null
                  ? Promise.resolve()
                  : onPatch(
                      row.original,
                      { account_id },
                      { account_id, account: accountChoices.find((choice) => choice.id === account_id)?.name ?? '' },
                    )
              }
              placeholder="Account"
              value={row.original.account_id}
            />
          ),
        }),
        helper.accessor('source', {
          id: 'source',
          header: 'Source',
          meta: { width: '5.5rem' },
          cell: ({ row }) => (
            <span className="flex h-7 items-center px-1.5 text-muted-foreground text-xs capitalize">{row.original.source}</span>
          ),
        }),
      ]),
    [accountChoices, categories, categoryChoices, expandedId, onExpand, onPatch],
  )

  const table = useTable({
    features,
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { rowSelection: selection },
    onRowSelectionChange: (next) =>
      onSelectionChange(typeof next === 'function' ? next(selection) : next),
  })

  const template = useMemo(() => columns.map((column) => column.meta?.width ?? '1fr').join(' '), [columns])
  const modelRows = table.getRowModel().rows

  // The virtualizer spans the whole result, not only what is loaded: a drag of the scrollbar
  // shows placeholders and pulls the pages it lands on.
  const virtualizer = useVirtualizer({
    count: total,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  })

  const items = virtualizer.getVirtualItems()
  const lastVisible = items.at(-1)?.index ?? 0
  useEffect(() => {
    if (lastVisible >= modelRows.length - 1 && modelRows.length < total) onReachEnd()
  }, [lastVisible, modelRows.length, total, onReachEnd])

  // Below about 1024 wide, Account and Source sit past the right edge. The fade says so.
  const [columnsRight, setColumnsRight] = useState(false)
  useEffect(() => {
    const element = scroller.current
    if (!element) return
    const measure = () => setColumnsRight(element.scrollWidth - element.clientWidth - element.scrollLeft > 1)
    measure()
    element.addEventListener('scroll', measure, { passive: true })
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => {
      element.removeEventListener('scroll', measure)
      observer.disconnect()
    }
  }, [])

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        className="min-h-0 flex-1 overflow-auto [scrollbar-color:var(--border)_transparent] [scrollbar-width:thin]"
        ref={scroller}
      >
        <div className="min-w-[68rem] text-sm" role="table" aria-rowcount={total}>
          <div className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur" role="rowgroup">
            {table.getHeaderGroups().map((group) => (
              <div className="grid items-center" key={group.id} role="row" style={{ gridTemplateColumns: template }}>
                {group.headers.map((header) => (
                  <div
                    // One line per header, whatever the width: a wrapped header makes the whole
                    // header row taller than every row under it.
                    className="min-w-0 px-1 py-1 font-medium text-muted-foreground text-xs uppercase tracking-wide"
                    key={header.id}
                    role="columnheader"
                  >
                    <div className={cn('truncate', header.column.id !== 'select' && 'px-1.5 leading-7')}>
                      <table.FlexRender header={header} />
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="relative" style={{ height: virtualizer.getTotalSize() }}>
            {items.map((item) => {
              const row = modelRows[item.index]
              return (
                <div
                  className="absolute top-0 left-0 w-full"
                  data-index={item.index}
                  key={row?.id ?? `placeholder-${item.index}`}
                  ref={virtualizer.measureElement}
                  role="rowgroup"
                  style={{ transform: `translateY(${item.start}px)` }}
                >
                  {row ? (
                    <div
                      className={cn(
                        'border-b transition-colors',
                        row.getIsSelected() ? 'bg-primary/5' : 'hover:bg-muted/40',
                        expandedId === row.original.id && 'bg-muted/40',
                      )}
                    >
                      <div className="grid items-start" role="row" style={{ gridTemplateColumns: template }}>
                        {row.getAllCells().map((cell) => (
                          <div className="min-w-0 px-1 py-1" key={cell.id} role="cell">
                            <table.FlexRender cell={cell} />
                          </div>
                        ))}
                      </div>
                      {expandedId === row.original.id && (
                        <SplitEditor
                          categories={categories}
                          onChanged={onSplitChanged}
                          transaction={row.original}
                        />
                      )}
                    </div>
                  ) : (
                    <div className="flex h-9 items-center border-b px-2" role="row">
                      <span className="h-3 w-40 animate-pulse rounded bg-muted" role="cell" />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
      {columnsRight && (
        <>
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 right-0 w-12 bg-gradient-to-l from-background to-transparent"
          />
          <Badge className="pointer-events-none absolute right-2 bottom-2 bg-background/90 font-normal text-muted-foreground" variant="outline">
            Scroll for more columns
          </Badge>
        </>
      )}
    </div>
  )
}
