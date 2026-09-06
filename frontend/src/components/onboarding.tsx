import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import type { FileUIPart } from 'ai'
import { CheckIcon, InfoIcon, PlusIcon, SparklesIcon } from 'lucide-react'
import { useRef, useState } from 'react'

import { Composer } from '@/components/composer'
import { ConfirmDialog, NameDialog } from '@/components/dialogs'
import { CategoryMenu, SubcategoryPill } from '@/components/taxonomy-menus'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldTitle,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  applyChangeset,
  categoriesQuery,
  conversationsQuery,
  createConversation,
  discardChangeset,
  loadSampleYear,
  openWelcome,
  patchSettings,
  proposeTaxonomyChange,
  settingsQuery,
  transactionCountQuery,
  type AnswerLanguage,
  type CategoryRef,
  type Changeset,
  type ModelKey,
  type TaxonomyChange,
} from '@/lib/api'
import { stashPendingPrompt } from '@/lib/pending'
import { useCatalog } from '@/lib/catalog'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/lib/workspace'

const FIRST_STEP = 1
const LAST_STEP = 4
const TITLES = ['Your categories', 'How I should answer', 'Your first data', 'That is everything']

const LANGUAGES: { value: AnswerLanguage; label: string }[] = [
  { value: 'follow', label: 'Follow my message' },
  { value: 'de', label: 'Deutsch' },
  { value: 'en', label: 'English' },
]

/** The message a file dropped here is sent with, the same one the composer sends for a bare file. */
const IMPORT_PROMPT = 'Import this.'

/** The one category automation never assigns, so the user never turns it off here either. */
const UNKNOWN = 'Unknown'

export const clampStep = (step: unknown) => {
  const value = Math.trunc(Number(step))
  return Number.isFinite(value) && value >= FIRST_STEP && value <= LAST_STEP ? value : FIRST_STEP
}

/**
 * The three steps and the finish a new profile opens with.
 *
 * Nothing here is a second way to do something the app already does. The categories are edited
 * through the changesets the Settings taxonomy editor proposes, the preferences are one PATCH
 * of the settings the Settings page writes, a dropped file goes to a new conversation through
 * `lib/pending` exactly as it does on the empty page, and the sample year and the welcome are
 * two conversations the server seeds.
 *
 * The step is in the URL, so a reload resumes where the user was and Back is the browser's own.
 */
export function OnboardingPage({ step }: { step: number }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { profile } = useWorkspace()
  const [leaving, setLeaving] = useState(false)
  const [error, setError] = useState<string>()

  const goTo = (next: number) => navigate({ to: '/onboarding', search: { step: clampStep(next) } })

  /** Leave the flow: write the state it ends in, then open the chat it hands over to. */
  const finish = async (state: 'done' | 'skipped', to?: string) => {
    if (!profile || leaving) return
    setLeaving(true)
    setError(undefined)
    try {
      await patchSettings(profile.id, { onboarding_state: state })
      await queryClient.invalidateQueries(settingsQuery(profile.id))
      await queryClient.invalidateQueries(conversationsQuery(profile.id))
      if (to) await navigate({ to: '/c/$conversationId', params: { conversationId: to } })
      else await navigate({ to: '/' })
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That did not work.')
    } finally {
      setLeaving(false)
    }
  }

  const openFirstChat = async () => {
    if (!profile || leaving) return
    try {
      const welcome = await openWelcome(profile.id)
      await finish('done', welcome.conversation_id)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The first chat could not be opened.')
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-6 py-10">
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-muted-foreground text-xs">
              {step > LAST_STEP - 1 ? 'Setup' : `Step ${step} of ${LAST_STEP - 1}`}
            </p>
            <Button
              disabled={leaving}
              onClick={() => void finish('skipped')}
              size="sm"
              variant="ghost"
            >
              Skip setup
            </Button>
          </div>
          <div className="flex gap-1.5" aria-hidden="true">
            {[1, 2, 3].map((mark) => (
              <span
                className={cn('h-1 flex-1 rounded-full', mark <= step ? 'bg-primary' : 'bg-muted')}
                key={mark}
              />
            ))}
          </div>
          <h1 className="font-heading font-semibold text-2xl tracking-tight">{TITLES[step - 1]}</h1>
        </div>

        {error && (
          <p className="text-destructive text-xs" role="alert">
            {error}
          </p>
        )}

        {step === 1 && <CategoriesStep />}
        {step === 2 && <PreferencesStep />}
        {step === 3 && <FirstDataStep busy={leaving} onImported={(id) => void finish('done', id)} />}
        {step === 4 && <FinishStep />}

        <div className="flex items-center justify-between gap-3">
          <Button
            disabled={step === FIRST_STEP || leaving}
            onClick={() => void goTo(step - 1)}
            variant="outline"
          >
            Back
          </Button>
          {step === LAST_STEP ? (
            <Button disabled={leaving || !profile} onClick={() => void openFirstChat()}>
              {leaving ? <Spinner data-icon="inline-start" /> : <SparklesIcon data-icon="inline-start" />}
              Open my first chat
            </Button>
          ) : (
            <Button
              disabled={leaving}
              onClick={() => void goTo(step + 1)}
              variant={step === 3 ? 'outline' : 'default'}
            >
              {step === 3 ? 'I will import later' : 'Continue'}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

/** A proposal waiting for a yes: it would move bookings, so it says how many first. */
interface Confirming {
  changeset: Changeset
  action: string
  after?: () => void | Promise<void>
}

const takesAwayLabel = (operation: TaxonomyChange['operation']) =>
  operation === 'merge' ? 'Merge' : 'Delete'

/** Step 1. Every toggle, add, rename and delete is a taxonomy changeset, applied straight away. */
function CategoriesStep() {
  const queryClient = useQueryClient()
  const { profile } = useWorkspace()
  const { data: categories } = useQuery(categoriesQuery(profile?.id))
  const [removed, setRemoved] = useState<{ at: number; category: CategoryRef }[]>([])
  const [adding, setAdding] = useState<{ category?: string }>()
  const [renaming, setRenaming] = useState<{ category: string; subcategory?: string }>()
  const [confirming, setConfirming] = useState<Confirming>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState<string>()
  // The dialog answers once: its Confirm both applies and closes, and the close must not then
  // discard what was just applied.
  const decided = useRef<string>(undefined)

  const change = async (title: string, taxonomy: TaxonomyChange) => {
    if (!profile) return
    setError(undefined)
    const proposed = await proposeTaxonomyChange(profile.id, title, taxonomy)
    await apply(proposed)
  }

  const apply = async (changeset: Changeset) => {
    if (!profile) return
    await applyChangeset(profile.id, changeset.id)
    await queryClient.invalidateQueries(categoriesQuery(profile.id))
    // A delete or a merge moved bookings to Needs review, so the transactions page is stale too.
    await queryClient.invalidateQueries({ queryKey: ['transactions'] })
  }

  const run = async (
    key: string,
    title: string,
    taxonomy: TaxonomyChange,
    after?: () => void | Promise<void>,
  ) => {
    if (!profile) return
    setBusy(key)
    setError(undefined)
    try {
      const proposed = await proposeTaxonomyChange(profile.id, title, taxonomy)
      // A change that takes a name away moves the bookings under it, so the count comes first.
      // A profile being set up usually has none, and then it just runs.
      const takesAway = taxonomy.operation === 'delete' || taxonomy.operation === 'merge'
      if (takesAway && proposed.total > 0) {
        setConfirming({ changeset: proposed, action: takesAwayLabel(taxonomy.operation), after })
        return
      }
      await apply(proposed)
      await after?.()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That did not work.')
    } finally {
      setBusy(undefined)
    }
  }

  /** Answer the confirmation: apply what was previewed, or discard it so it cannot linger. */
  const settle = async (confirm: boolean) => {
    const item = confirming
    if (!profile || !item || decided.current === item.changeset.id) return
    decided.current = item.changeset.id
    setConfirming(undefined)
    try {
      if (confirm) {
        await apply(item.changeset)
        await item.after?.()
      } else {
        await discardChangeset(profile.id, item.changeset.id).catch(() => undefined)
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That did not work.')
    }
  }

  /** A category is really gone, so every row kept below it moves up one place. */
  const closeGap = (at: number) =>
    setRemoved((rows) => rows.map((row) => (row.at > at ? { ...row, at: row.at - 1 } : row)))

  // A category the user turned off is gone from the profile, so its shape and its place in the
  // list are kept here: the row stays where it was, off, in case they change their mind.
  const toggle = (category: CategoryRef, on: boolean, at: number) => {
    if (!on) {
      void run(category.id, `Remove ${category.name}`, { operation: 'delete', category: category.name }, () =>
        setRemoved((rows) => [...rows, { at, category }]),
      )
      return
    }
    void run(category.id, `Add ${category.name}`, { operation: 'add', category: category.name }, async () => {
      for (const subcategory of category.subcategories) {
        await change(`Add ${subcategory.name}`, {
          operation: 'add',
          category: category.name,
          subcategory: subcategory.name,
        })
      }
      setRemoved((rows) => rows.filter((row) => row.category.id !== category.id))
    })
  }

  // Unknown is not a choice: it is the category a human assigns when a booking fits nowhere, so
  // it is explained under the list rather than offered as a toggle that could turn it off.
  const rows = (categories ?? []).filter((category) => category.name !== UNKNOWN)
  for (const row of [...removed].sort((a, b) => a.at - b.at)) rows.splice(row.at, 0, row.category)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Which of these do you use?</CardTitle>
        <CardDescription>
          All of them are on. Turn off what you do not need, click a name to rename it, and add your own.
          Off removes a category from this profile; Delete does the same for one you added. You can change
          all of it later in Settings.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error && (
          <p className="text-destructive text-xs" role="alert">
            {error}
          </p>
        )}
        <ul className="divide-y rounded-lg border">
          {rows.map((category, at) => {
            const on = !removed.some((row) => row.category.id === category.id)
            return (
              <li className="flex items-start justify-between gap-3 px-3 py-2.5" key={category.id}>
                <div className={cn('min-w-0 flex-1', !on && 'opacity-50')}>
                  {renaming?.category === category.name && renaming.subcategory === undefined ? (
                    <RenameInput
                      label="Category name"
                      name={category.name}
                      onCancel={() => setRenaming(undefined)}
                      onRename={(next) => {
                        setRenaming(undefined)
                        void run(category.id, `Rename ${category.name} to ${next}`, {
                          operation: 'rename',
                          category: category.name,
                          new_name: next,
                        })
                      }}
                    />
                  ) : (
                    <button
                      aria-label={`Rename ${category.name}`}
                      className="rounded-sm text-left font-medium text-sm transition-colors hover:text-primary focus-ring disabled:hover:text-foreground"
                      disabled={!on}
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
                          onRename={(next) => {
                            setRenaming(undefined)
                            void run(subcategory.id, `Rename ${subcategory.name} to ${next}`, {
                              operation: 'rename',
                              category: category.name,
                              subcategory: subcategory.name,
                              new_name: next,
                            })
                          }}
                        />
                      ) : (
                        // The same pill and menu the Settings taxonomy editor draws, so the two read
                        // as one and a subcategory goes the same way in both.
                        <SubcategoryPill
                          category={category}
                          disabled={!on}
                          key={subcategory.id}
                          onDelete={() =>
                            void run(subcategory.id, `Delete ${subcategory.name}`, {
                              operation: 'delete',
                              category: category.name,
                              subcategory: subcategory.name,
                            })
                          }
                          onMerge={(into) =>
                            void run(subcategory.id, `Merge ${subcategory.name} into ${into}`, {
                              operation: 'merge',
                              category: category.name,
                              subcategory: subcategory.name,
                              into,
                            })
                          }
                          onRename={() => setRenaming({ category: category.name, subcategory: subcategory.name })}
                          subcategory={subcategory}
                        />
                      ),
                    )}
                    {on && (
                      <Button
                        aria-label={`Add a subcategory to ${category.name}`}
                        className="rounded-full border-dashed text-muted-foreground"
                        onClick={() => setAdding({ category: category.name })}
                        size="xs"
                        variant="outline"
                      >
                        <PlusIcon aria-hidden="true" data-icon="inline-start" />
                        Subcategory
                      </Button>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Switch
                    aria-label={category.name}
                    checked={on}
                    disabled={busy === category.id}
                    onCheckedChange={(next) => toggle(category, next, at)}
                  />
                  {/* A row that is off is not in the taxonomy any more, so there is nothing to
                      change about it until the switch brings it back. */}
                  {on && (
                    <CategoryMenu
                      categories={categories ?? []}
                      category={category}
                      onAddSubcategory={() => setAdding({ category: category.name })}
                      onDelete={() =>
                        void run(
                          category.id,
                          `Delete ${category.name}`,
                          { operation: 'delete', category: category.name },
                          () => closeGap(at),
                        )
                      }
                      onMerge={(into) =>
                        void run(
                          category.id,
                          `Merge ${category.name} into ${into}`,
                          { operation: 'merge', category: category.name, into },
                          () => closeGap(at),
                        )
                      }
                      onRename={() => setRenaming({ category: category.name })}
                    />
                  )}
                </div>
              </li>
            )
          })}
        </ul>

        <Button className="self-start" onClick={() => setAdding({})} size="sm" variant="outline">
          <PlusIcon data-icon="inline-start" /> Add a category
        </Button>

        <Alert>
          <InfoIcon />
          <AlertTitle>Needs review and Unknown are not on this list</AlertTitle>
          <AlertDescription>
            Needs review is what a booking is until it has a category, not a category itself. Unknown is a
            real one you can assign when something fits nowhere, and I never assign it for you.
          </AlertDescription>
        </Alert>
      </CardContent>

      <NameDialog
        action={adding?.category ? 'Add subcategory' : 'Add category'}
        description={
          adding?.category
            ? `A new subcategory of ${adding.category}.`
            : 'A new category for this profile, with subcategories you can add to it.'
        }
        key={adding?.category ?? 'new-category'}
        onOpenChange={(open) => setAdding(open ? adding : undefined)}
        onSubmit={async (name) => {
          await run('adding', `Add ${name}`, {
            operation: 'add',
            category: adding?.category ?? name,
            subcategory: adding?.category ? name : null,
          })
        }}
        open={adding !== undefined}
        placeholder="Name"
        title={adding?.category ? `New subcategory in ${adding.category}` : 'New category'}
      />

      <ConfirmDialog
        action={confirming?.action ?? 'Apply'}
        description={confirming ? `${confirming.changeset.summary} ${confirming.changeset.note ?? ''}`.trim() : ''}
        key={confirming?.changeset.id ?? 'nothing-to-confirm'}
        onConfirm={() => settle(true)}
        onOpenChange={(open) => void (open ? undefined : settle(false))}
        open={confirming !== undefined}
        title={confirming?.changeset.title ?? ''}
      />
    </Card>
  )
}

/** Step 2. The three preferences that shape the assistant, written as one PATCH each. */
function PreferencesStep() {
  const queryClient = useQueryClient()
  const { profile } = useWorkspace()
  const { data: settings } = useQuery(settingsQuery(profile?.id))
  const [error, setError] = useState<string>()
  const { entries, defaultKey } = useCatalog()

  const write = async (patch: Parameters<typeof patchSettings>[1]) => {
    if (!profile) return
    setError(undefined)
    try {
      const next = await patchSettings(profile.id, patch)
      queryClient.setQueryData(settingsQuery(profile.id).queryKey, next)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That could not be saved.')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Three things that shape my answers</CardTitle>
        <CardDescription>Every one of them is in Settings too, so nothing here is final.</CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="pb-3 text-destructive text-xs" role="alert">
            {error}
          </p>
        )}
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="answer-language">Answer language</FieldLabel>
            <FieldDescription>
              Follow my message means a German question gets a German answer and an English one an English
              answer, in the same chat.
            </FieldDescription>
            <Choices
              id="answer-language"
              onChange={(value) => void write({ answer_language: value as AnswerLanguage })}
              options={LANGUAGES}
              value={settings?.answer_language ?? 'follow'}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="default-model">Model for new chats</FieldLabel>
            <FieldDescription>
              Four to choose from, on this machine or in the cloud, and you can switch a chat to another one
              at any time. Tools always run on the fast model of whichever provider the chat is on. One that
              is not ready says why.
            </FieldDescription>
            <Choices
              id="default-model"
              onChange={(value) => void write({ default_model_key: value as ModelKey })}
              options={entries.map((model) => ({
                value: model.key,
                label: model.label,
                disabled: !model.available,
                title: model.reason ?? undefined,
              }))}
              value={settings?.default_model_key ?? defaultKey ?? ''}
            />
          </Field>

          <Field className="items-start" orientation="horizontal">
            <FieldContent>
              <FieldTitle>Look merchants up on the web</FieldTitle>
              <FieldDescription>
                Off by default. When it is on and I meet a merchant I do not know, only a scrubbed merchant
                name leaves this machine: never an amount, a date, an account number or a person's name.
                Every request is written to the outbound log in Settings before it is sent.
              </FieldDescription>
            </FieldContent>
            <Switch
              aria-label="Web lookup"
              checked={settings?.web_lookup_enabled ?? false}
              disabled={!settings}
              id="web-lookup"
              onCheckedChange={(next) => void write({ web_lookup_enabled: next })}
            />
          </Field>
        </FieldGroup>
      </CardContent>
    </Card>
  )
}

/** One row of choices. The check is what tells the chosen one apart at a glance. */
function Choices({
  id,
  options,
  value,
  onChange,
}: {
  id: string
  /** `disabled` with a `title` is how an unavailable model is offered: listed, with the reason. */
  options: { value: string; label: string; disabled?: boolean; title?: string }[]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <ToggleGroup
      id={id}
      onValueChange={(next) => next && onChange(next)}
      type="single"
      value={value}
      variant="outline"
    >
      {options.map((option) => (
        <ToggleGroupItem disabled={option.disabled} key={option.value} title={option.title} value={option.value}>
          {option.value === value ? <CheckIcon data-icon="inline-start" /> : null}
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}

/** Step 3. A file dropped here takes the same road as a file dropped into the composer. */
function FirstDataStep({ busy, onImported }: { busy: boolean; onImported: (conversationId: string) => void }) {
  const queryClient = useQueryClient()
  const { profile } = useWorkspace()
  const { data: settings } = useQuery(settingsQuery(profile?.id))
  const [modelKey, setModelKey] = useState<ModelKey>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>()
  const chosen = modelKey ?? settings?.default_model_key

  const start = async (text: string, files: FileUIPart[]) => {
    if (!profile || loading || busy) return
    setLoading(true)
    try {
      const conversation = await createConversation(profile.id, chosen ?? null)
      stashPendingPrompt(conversation.id, { text: text || IMPORT_PROMPT, files })
      onImported(conversation.id)
    } finally {
      setLoading(false)
    }
  }

  const sample = async () => {
    if (!profile || loading || busy) return
    setLoading(true)
    setError(undefined)
    try {
      const opened = await loadSampleYear(profile.id)
      await queryClient.invalidateQueries(transactionCountQuery(profile.id))
      onImported(opened.conversation_id)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The sample year could not be imported.')
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Drop a statement in</CardTitle>
        <CardDescription>
          A CSV export, a statement PDF or a photo of a bill. I open a chat with it, read it, show you how I
          read the columns and ask about anything I am unsure of. Nothing is imported behind your back.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className={cn(loading && 'pointer-events-none opacity-60')}>
          <Composer
            modelKey={chosen}
            onModelChange={setModelKey}
            onSubmit={start}
            status={loading || busy ? 'submitted' : 'ready'}
          />
        </div>

        <div className="flex items-center gap-3">
          <Separator className="flex-1" />
          <span className="text-muted-foreground text-xs">or try it out first</span>
          <Separator className="flex-1" />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
          <div className="min-w-0">
            <p className="font-medium text-sm">No statement to hand?</p>
            <p className="text-muted-foreground text-xs">
              A synthetic German household, one full year of bookings. Made up numbers, no real person.
            </p>
          </div>
          <Button disabled={loading || busy || !profile} onClick={() => void sample()}>
            {loading ? <Spinner data-icon="inline-start" /> : null}
            Load the sample year
          </Button>
        </div>
        {error && (
          <p className="text-destructive text-xs" role="alert">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/** The finish. The welcome turn behind the button is written by the server, not by a model. */
function FinishStep() {
  const { profile } = useWorkspace()
  const { data: bookings } = useQuery(transactionCountQuery(profile?.id))

  return (
    <Card>
      <CardHeader>
        <CardTitle>You are set up</CardTitle>
        <CardDescription>
          {bookings
            ? `${bookings} bookings are in this profile. Ask about them in your own words.`
            : 'Nothing is imported yet, and that is fine: drop a file into any chat and I will read it.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2 text-muted-foreground text-sm">
          <li className="flex items-start gap-2">
            <CheckIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
            Every number I state comes from a query you can open and read.
          </li>
          <li className="flex items-start gap-2">
            <CheckIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
            Your data stays on this machine unless you switch web lookup on.
          </li>
          <li className="flex items-start gap-2">
            <CheckIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
            When I am unsure I ask you in the chat instead of guessing.
          </li>
        </ul>
      </CardContent>
    </Card>
  )
}

/** Enter renames, Escape and losing focus give up: the same inline rename Settings uses. */
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

/** The Settings entry that reopens the flow, whether it was finished or skipped. */
export function OnboardingCard() {
  const navigate = useNavigate()
  const { profile } = useWorkspace()
  const { data: settings } = useQuery(settingsQuery(profile?.id))
  const state = settings?.onboarding_state

  return (
    <section aria-labelledby="setup-heading" className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-heading font-semibold text-base" id="setup-heading">
            Setup
          </h2>
          <p className="max-w-xl text-muted-foreground text-xs">
            {state === 'skipped'
              ? 'You skipped the short setup. It picks your categories, the language I answer in and gets your first file in.'
              : 'The short setup: which categories you use, the language I answer in, and your first file. Nothing you do in it is final.'}
          </p>
        </div>
        <Button
          disabled={!profile}
          onClick={() => void navigate({ to: '/onboarding', search: { step: FIRST_STEP } })}
          size="sm"
          variant="outline"
        >
          {state === 'not_started' ? 'Start setup' : 'Run setup again'}
        </Button>
      </div>
    </section>
  )
}
