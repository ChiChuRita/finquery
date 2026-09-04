import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { CheckIcon, ChevronsUpDownIcon, PencilIcon, PlusIcon, Trash2Icon, UserRoundIcon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmDialog, NameDialog } from '@/components/dialogs'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { createProfile, deleteProfile, profilesQuery, renameProfile } from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'
import { cn } from '@/lib/utils'

export function ProfileSwitcher() {
  const { profile, profiles, switchProfile } = useWorkspace()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [dialog, setDialog] = useState<'create' | 'rename' | 'delete'>()

  const refresh = () => queryClient.invalidateQueries(profilesQuery)

  // The open conversation belongs to the profile we are leaving, so leave it first: while it is
  // still on screen it would pull the sidebar straight back to its own profile.
  const leaveConversation = () => navigate({ to: '/' })

  const select = async (profileId: string) => {
    if (profileId === profile?.id) return
    await leaveConversation()
    switchProfile(profileId)
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button aria-label="Switch profile" className="h-9 w-full justify-start gap-2 px-2" variant="ghost">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <UserRoundIcon className="size-3.5" />
            </span>
            <span className="min-w-0 flex-1 truncate text-left text-sm">{profile?.name ?? 'Loading...'}</span>
            <ChevronsUpDownIcon className="size-3.5 shrink-0 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56" side="top">
          <DropdownMenuLabel className="text-muted-foreground text-xs">Profiles</DropdownMenuLabel>
          {profiles.map((p) => (
            <DropdownMenuItem key={p.id} onSelect={() => void select(p.id)}>
              <span className="min-w-0 flex-1 truncate">{p.name}</span>
              <CheckIcon className={cn('size-4 text-primary', p.id !== profile?.id && 'invisible')} />
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setDialog('create')}>
            <PlusIcon className="size-4" />
            New profile
          </DropdownMenuItem>
          <DropdownMenuItem disabled={!profile} onSelect={() => setDialog('rename')}>
            <PencilIcon className="size-4" />
            Rename profile
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={profiles.length < 2}
            onSelect={() => setDialog('delete')}
            variant="destructive"
          >
            <Trash2Icon className="size-4" />
            Delete profile
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <NameDialog
        action="Create profile"
        description="Accounts, transactions, categories and conversations stay inside one profile."
        onOpenChange={(open) => setDialog(open ? 'create' : undefined)}
        onSubmit={async (name) => {
          const created = await createProfile(name)
          await refresh()
          await leaveConversation()
          switchProfile(created.id)
        }}
        open={dialog === 'create'}
        placeholder="Household"
        title="New profile"
      />

      <NameDialog
        action="Rename"
        initial={profile?.name ?? ''}
        onOpenChange={(open) => setDialog(open ? 'rename' : undefined)}
        onSubmit={async (name) => {
          if (profile) await renameProfile(profile.id, name)
          await refresh()
        }}
        open={dialog === 'rename'}
        title="Rename profile"
      />

      <ConfirmDialog
        action="Delete profile"
        description={`Everything in ${profile?.name ?? 'this profile'}, including its conversations, is deleted. This cannot be undone.`}
        onConfirm={async () => {
          if (!profile) return
          const next = profiles.find((p) => p.id !== profile.id)
          await leaveConversation()
          await deleteProfile(profile.id)
          await refresh()
          if (next) switchProfile(next.id)
        }}
        onOpenChange={(open) => setDialog(open ? 'delete' : undefined)}
        open={dialog === 'delete'}
        title="Delete profile?"
      />
    </>
  )
}
