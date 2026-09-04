import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontalIcon, PlusIcon } from 'lucide-react'
import { useState } from 'react'

import { ChangesetEffect } from '@/components/changeset-card'
import { NameDialog } from '@/components/dialogs'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  applyChangeset,
  categoriesQuery,
  discardChangeset,
  proposeTaxonomyChange,
  type CategoryRef,
  type Changeset,
  type TaxonomyChange,
} from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'

interface Naming {
  category: string
  subcategory?: string
}

/** The profile's own taxonomy, edited through the same changesets the assistant proposes. */
export function TaxonomyCard() {
  const { profile } = useWorkspace()
  const queryClient = useQueryClient()
  const { data: categories } = useQuery(categoriesQuery(profile?.id))
  const [pending, setPending] = useState<Changeset>()
  const [adding, setAdding] = useState<{ category?: string }>()
  const [renaming, setRenaming] = useState<Naming>()
  const [error, setError] = useState<string>()

  const refresh = async () => {
    await queryClient.invalidateQueries(categoriesQuery(profile?.id))
    // A merge or a delete moved rows, so the transactions page is stale as well.
    await queryClient.invalidateQueries({ queryKey: ['transactions'] })
  }

  const start = async (title: string, taxonomy: TaxonomyChange) => {
    if (!profile) return
    setError(undefined)
    setRenaming(undefined)
    try {
      const proposed = await proposeTaxonomyChange(profile.id, title, taxonomy)
      // Adding a name touches no existing booking, so there is nothing to weigh up first.
      if (taxonomy.operation === 'add') {
        await applyChangeset(profile.id, proposed.id)
        await refresh()
        return
      }
      setPending(proposed)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That did not work.')
    }
  }

  const close = async (confirm: boolean) => {
    const changeset = pending
    setPending(undefined)
    if (!changeset || !profile) return
    if (confirm) {
      await applyChangeset(profile.id, changeset.id)
      await refresh()
    } else {
      // A proposal nobody applied is discarded, so it cannot linger and be applied later.
      await discardChangeset(profile.id, changeset.id).catch(() => undefined)
    }
  }

  return (
    <section aria-labelledby="taxonomy-heading" className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-heading font-semibold text-base" id="taxonomy-heading">
            Categories
          </h2>
          <p className="text-muted-foreground text-xs">
            One level deep, and yours. Every change shows what it does to your bookings before it
            happens, the same card the assistant proposes in a chat.
          </p>
        </div>
        <Button onClick={() => setAdding({})} size="sm" variant="outline">
          <PlusIcon /> Add a category
        </Button>
      </div>

      {error && (
        <p className="pt-3 text-destructive text-xs" role="alert">
          {error}
        </p>
      )}

      <ul className="mt-3 divide-y rounded-lg border">
        {(categories ?? []).map((category) => (
          <li className="px-3 py-2.5" key={category.id}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                {renaming?.category === category.name && renaming.subcategory === undefined ? (
                  <RenameInput
                    label="Category name"
                    name={category.name}
                    onCancel={() => setRenaming(undefined)}
                    onRename={(next) =>
                      void start(`Rename ${category.name} to ${next}`, {
                        operation: 'rename',
                        category: category.name,
                        new_name: next,
                      })
                    }
                  />
                ) : (
                  <button
                    className="text-left font-medium text-sm hover:text-primary"
                    onClick={() => setRenaming({ category: category.name })}
                    title="Click to rename"
                    type="button"
                  >
                    {category.name}
                  </button>
                )}
                <div className="flex flex-wrap items-center gap-1.5 pt-1.5">
                  {category.subcategories.map((subcategory) =>
                    renaming?.category === category.name && renaming.subcategory === subcategory.name ? (
                      <RenameInput
                        key={subcategory.id}
                        label="Subcategory name"
                        name={subcategory.name}
                        onCancel={() => setRenaming(undefined)}
                        onRename={(next) =>
                          void start(`Rename ${subcategory.name} to ${next}`, {
                            operation: 'rename',
                            category: category.name,
                            subcategory: subcategory.name,
                            new_name: next,
                          })
                        }
                      />
                    ) : (
                      <DropdownMenu key={subcategory.id}>
                        <DropdownMenuTrigger asChild>
                          <button
                            className="rounded-full border px-2 py-0.5 text-xs transition-colors hover:bg-accent"
                            type="button"
                          >
                            {subcategory.name}
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                          <DropdownMenuItem
                            onSelect={() => setRenaming({ category: category.name, subcategory: subcategory.name })}
                          >
                            Rename
                          </DropdownMenuItem>
                          {category.subcategories.length > 1 && (
                            <DropdownMenuSub>
                              <DropdownMenuSubTrigger>Merge into</DropdownMenuSubTrigger>
                              <DropdownMenuSubContent>
                                {category.subcategories
                                  .filter((other) => other.id !== subcategory.id)
                                  .map((other) => (
                                    <DropdownMenuItem
                                      key={other.id}
                                      onSelect={() =>
                                        void start(`Merge ${subcategory.name} into ${other.name}`, {
                                          operation: 'merge',
                                          category: category.name,
                                          subcategory: subcategory.name,
                                          into: other.name,
                                        })
                                      }
                                    >
                                      {other.name}
                                    </DropdownMenuItem>
                                  ))}
                              </DropdownMenuSubContent>
                            </DropdownMenuSub>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onSelect={() =>
                              void start(`Delete ${subcategory.name}`, {
                                operation: 'delete',
                                category: category.name,
                                subcategory: subcategory.name,
                              })
                            }
                            variant="destructive"
                          >
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    ),
                  )}
                  <button
                    className="rounded-full border border-dashed px-2 py-0.5 text-muted-foreground text-xs transition-colors hover:bg-accent hover:text-foreground"
                    onClick={() => setAdding({ category: category.name })}
                    type="button"
                  >
                    <PlusIcon aria-hidden="true" className="mr-0.5 inline size-3" />
                    Subcategory
                  </button>
                </div>
              </div>

              <CategoryMenu
                categories={categories ?? []}
                category={category}
                onAddSubcategory={() => setAdding({ category: category.name })}
                onDelete={() =>
                  void start(`Delete ${category.name}`, { operation: 'delete', category: category.name })
                }
                onMerge={(into) =>
                  void start(`Merge ${category.name} into ${into}`, {
                    operation: 'merge',
                    category: category.name,
                    into,
                  })
                }
                onRename={() => setRenaming({ category: category.name })}
              />
            </div>
          </li>
        ))}
      </ul>

      <NameDialog
        action={adding?.category ? 'Add subcategory' : 'Add category'}
        description={
          adding?.category
            ? `A new subcategory of ${adding.category}. No existing booking is touched.`
            : 'A new category for this profile. No existing booking is touched.'
        }
        key={adding?.category ?? 'new-category'}
        onOpenChange={(open) => setAdding(open ? adding : undefined)}
        onSubmit={async (name) => {
          await start(`Add ${name}`, {
            operation: 'add',
            category: adding?.category ?? name,
            subcategory: adding?.category ? name : null,
          })
        }}
        open={adding !== undefined}
        placeholder="Name"
        title={adding?.category ? `New subcategory in ${adding.category}` : 'New category'}
      />

      <Dialog onOpenChange={(open) => void (open ? undefined : close(false))} open={pending !== undefined}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{pending?.title}</DialogTitle>
            <DialogDescription>This is what it does to the bookings you already have.</DialogDescription>
          </DialogHeader>
          {pending && <ChangesetEffect changeset={pending} />}
          <DialogFooter>
            <Button onClick={() => void close(false)} variant="outline">
              Cancel
            </Button>
            <Button onClick={() => void close(true)}>Apply</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}

function CategoryMenu({
  category,
  categories,
  onRename,
  onAddSubcategory,
  onMerge,
  onDelete,
}: {
  category: CategoryRef
  categories: CategoryRef[]
  onRename: () => void
  onAddSubcategory: () => void
  onMerge: (into: string) => void
  onDelete: () => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button aria-label={`Change ${category.name}`} size="icon-sm" variant="ghost">
          <MoreHorizontalIcon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onRename}>Rename</DropdownMenuItem>
        <DropdownMenuItem onSelect={onAddSubcategory}>Add a subcategory</DropdownMenuItem>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>Merge into</DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="max-h-72 overflow-y-auto">
            {categories
              .filter((other) => other.id !== category.id)
              .map((other) => (
                <DropdownMenuItem key={other.id} onSelect={() => onMerge(other.name)}>
                  {other.name}
                </DropdownMenuItem>
              ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onDelete} variant="destructive">
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** Enter renames, Escape and losing focus give up: a rename opens a dialog, so it must be asked for. */
function RenameInput({
  name,
  label,
  onRename,
  onCancel,
}: {
  name: string
  label: string
  onRename: (next: string) => void
  onCancel: () => void
}) {
  return (
    <Input
      aria-label={label}
      autoFocus
      className="h-7 w-48 text-sm"
      defaultValue={name}
      onBlur={onCancel}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onCancel()
        if (event.key !== 'Enter') return
        event.preventDefault()
        const next = event.currentTarget.value.trim()
        if (next && next !== name) onRename(next)
        else onCancel()
      }}
    />
  )
}
