import { MoreHorizontalIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
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
import type { CategoryRef, SubcategoryRef } from '@/lib/api'

/**
 * The two menus that edit a taxonomy, shared by the Settings card and onboarding.
 *
 * Neither of them knows what a change does: the editor around them proposes and applies the
 * changeset, so the two editors stay one implementation and a booking always moves the same way.
 */

/** The pill for one subcategory, and everything that can be done to it. */
export function SubcategoryPill({
  category,
  subcategory,
  disabled,
  onRename,
  onMerge,
  onDelete,
}: {
  category: CategoryRef
  subcategory: SubcategoryRef
  disabled?: boolean
  onRename: () => void
  onMerge: (into: string) => void
  onDelete: () => void
}) {
  const siblings = category.subcategories.filter((other) => other.id !== subcategory.id)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={`Change ${subcategory.name} in ${category.name}`}
          className="rounded-full"
          disabled={disabled}
          size="xs"
          variant="outline"
        >
          {subcategory.name}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuItem onSelect={onRename}>Rename</DropdownMenuItem>
        {siblings.length > 0 && (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>Merge into</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              {siblings.map((other) => (
                <DropdownMenuItem key={other.id} onSelect={() => onMerge(other.name)}>
                  {other.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onDelete} variant="destructive">
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** The menu at the end of a category row. `categories` is where a merge can go. */
export function CategoryMenu({
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
