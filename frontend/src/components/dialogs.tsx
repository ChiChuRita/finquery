import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

/** Ask for one name (a new profile, a renamed profile) and report what the server said. */
export function NameDialog({
  open,
  onOpenChange,
  title,
  description,
  initial = '',
  placeholder,
  action,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  initial?: string
  placeholder?: string
  action: string
  onSubmit: (name: string) => Promise<void>
}) {
  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <NameForm
          action={action}
          initial={initial}
          label={title}
          onDone={() => onOpenChange(false)}
          onSubmit={onSubmit}
          placeholder={placeholder}
        />
      </DialogContent>
    </Dialog>
  )
}

// Mounted with the open dialog, so it always starts from the current name.
function NameForm({
  initial,
  label,
  placeholder,
  action,
  onSubmit,
  onDone,
}: {
  initial: string
  label: string
  placeholder?: string
  action: string
  onSubmit: (name: string) => Promise<void>
  onDone: () => void
}) {
  const [name, setName] = useState(initial)
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    const value = name.trim()
    if (!value || busy) return
    setBusy(true)
    try {
      await onSubmit(value)
      onDone()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That did not work.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="space-y-2">
        <Input
          aria-label={label}
          autoFocus
          onChange={(event) => {
            setName(event.target.value)
            setError(undefined)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void submit()
            }
          }}
          placeholder={placeholder}
          value={name}
        />
        {error ? (
          <p className="text-destructive text-xs" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      <DialogFooter>
        <Button onClick={onDone} variant="outline">
          Cancel
        </Button>
        <Button disabled={!name.trim() || busy} onClick={() => void submit()}>
          {action}
        </Button>
      </DialogFooter>
    </>
  )
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  action,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  action: string
  onConfirm: () => Promise<void> | void
}) {
  const [busy, setBusy] = useState(false)

  const confirm = async () => {
    setBusy(true)
    try {
      await onConfirm()
      onOpenChange(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            Cancel
          </Button>
          <Button disabled={busy} onClick={() => void confirm()} variant="destructive">
            {action}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
