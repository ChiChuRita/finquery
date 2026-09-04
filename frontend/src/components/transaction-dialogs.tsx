import { useMutation } from '@tanstack/react-query'
import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { createTransaction, type AccountRef, type CategoryRef, type NewTransaction } from '@/lib/api'
import { parseAmount } from '@/lib/format'
import { useWorkspace } from '@/lib/workspace'

const NONE = '__none__'
const today = () => new Date().toISOString().slice(0, 10)

export function AddTransactionDialog({
  accounts,
  categories,
  onCreated,
}: {
  accounts: AccountRef[]
  categories: CategoryRef[]
  onCreated: () => void
}) {
  const { profile } = useWorkspace()
  const [open, setOpen] = useState(false)
  const [bookedOn, setBookedOn] = useState(today)
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [chosenAccount, setAccountId] = useState('')
  const [categoryId, setCategoryId] = useState(NONE)
  const [problem, setProblem] = useState<string | null>(null)
  // The accounts arrive with their own query, so the first one is the default until it is picked.
  const accountId = chosenAccount || accounts[0]?.id || ''

  const create = useMutation({
    mutationFn: (body: NewTransaction) => {
      if (!profile) throw new Error('No profile is active yet.')
      return createTransaction(profile.id, body)
    },
    onSuccess: () => {
      setOpen(false)
      setDescription('')
      setAmount('')
      setCategoryId(NONE)
      setBookedOn(today())
      setProblem(null)
      onCreated()
    },
    onError: (failure: Error) => setProblem(failure.message),
  })

  const submit = () => {
    setProblem(null)
    const cents = parseAmount(amount)
    if (!description.trim()) return setProblem('Give the transaction a description.')
    if (cents === null) return setProblem('An amount looks like -12,50. Money out is negative.')
    if (!accountId) return setProblem('Pick the account this booking belongs to.')
    create.mutate({
      booked_on: bookedOn,
      description: description.trim(),
      amount_cents: cents,
      account_id: accountId,
      category_id: categoryId === NONE ? null : categoryId,
    })
  }

  return (
    <Dialog onOpenChange={setOpen} open={open}>
      <DialogTrigger asChild>
        <Button
          disabled={accounts.length === 0}
          size="sm"
          title={accounts.length === 0 ? 'Import a statement first, so there is an account to book against.' : undefined}
        >
          <PlusIcon /> Add a transaction
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add a transaction</DialogTitle>
          <DialogDescription>
            For cash and anything else no statement knows about. It is saved with the source manual.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-xs" htmlFor="new-date">
                Date
              </Label>
              <Input
                id="new-date"
                onChange={(event) => setBookedOn(event.target.value)}
                type="date"
                value={bookedOn}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-xs" htmlFor="new-amount">
                Amount in euros
              </Label>
              <Input
                className="text-right tabular-nums"
                id="new-amount"
                onChange={(event) => setAmount(event.target.value)}
                placeholder="-12,50"
                value={amount}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-muted-foreground text-xs" htmlFor="new-description">
              Description
            </Label>
            <Input
              id="new-description"
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Lunch paid in cash"
              value={description}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-xs" htmlFor="new-account">
                Account
              </Label>
              <Select onValueChange={setAccountId} value={accountId}>
                <SelectTrigger className="w-full" id="new-account">
                  <SelectValue placeholder="Pick an account" />
                </SelectTrigger>
                <SelectContent>
                  {accounts.map((account) => (
                    <SelectItem key={account.id} value={account.id}>
                      {account.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-xs" htmlFor="new-category">
                Category
              </Label>
              <Select onValueChange={setCategoryId} value={categoryId}>
                <SelectTrigger className="w-full" id="new-category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  <SelectItem value={NONE}>Needs review</SelectItem>
                  <SelectSeparator />
                  {categories.map((category) => (
                    <SelectItem key={category.id} value={category.id}>
                      {category.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {problem && (
            <p className="text-destructive text-xs" role="alert">
              {problem}
            </p>
          )}
        </div>

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button disabled={create.isPending} onClick={submit}>
            {create.isPending ? 'Saving...' : 'Add it'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ConfirmDeleteDialog({
  count,
  pending,
  onConfirm,
}: {
  count: number
  pending: boolean
  onConfirm: () => Promise<unknown>
}) {
  const [open, setOpen] = useState(false)

  return (
    <Dialog onOpenChange={setOpen} open={open}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Trash2Icon /> Delete
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {count === 1 ? 'this transaction' : `these ${count} transactions`}?</DialogTitle>
          <DialogDescription>
            Deleting is permanent, and a transaction with a split takes its legs with it. Importing the
            statement again is the only way back.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">{count === 1 ? 'Keep it' : 'Keep them'}</Button>
          </DialogClose>
          <Button
            disabled={pending}
            variant="destructive"
            onClick={async () => {
              await onConfirm()
              setOpen(false)
            }}
          >
            {pending ? 'Deleting...' : count === 1 ? 'Delete it' : `Delete ${count}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
