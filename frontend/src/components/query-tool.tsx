import { Tool, ToolContent, ToolHeader } from '@/components/ai-elements/tool'
import { ErrorSection, RowsTable, Section, SqlSection, rowLabel } from '@/components/query-result'
import type { QueryToolOutput, QueryToolPart } from '@/lib/api'

function title(part: QueryToolPart) {
  if (part.state === 'output-error') return 'Query failed'
  if (part.state !== 'output-available') return 'Querying your transactions'
  return part.output.error ? 'Query refused' : `Query · ${rowLabel(part.output.row_count)}`
}

/** What this step is, for someone who has never read a line about the app. */
const WHAT_IT_IS =
  'A sub-agent wrote this SQL from the request, a guard admitted it as a read-only SELECT over '
  + 'your own transactions, and these are the rows it came back with. Every figure in the answer '
  + 'is one of them.'

function Result({ output, hints }: { output: QueryToolOutput; hints?: string | null }) {
  return (
    <>
      <p className="text-muted-foreground text-xs">{WHAT_IT_IS}</p>
      <Section label="Request">
        <p className="text-sm">{output.request}</p>
        {hints && <p className="text-muted-foreground text-sm">Hints: {hints}</p>}
      </Section>
      {output.sql && <SqlSection sql={output.sql} />}
      {output.error ? (
        <ErrorSection message={output.error} />
      ) : (
        <Section label={`Result · ${rowLabel(output.row_count)}`}>
          <RowsTable columns={output.columns} rows={output.rows} />
        </Section>
      )}
    </>
  )
}

/** One executed query in the transcript: the request, the SQL, the row count and the rows. */
export function QueryToolStep({ part }: { part: QueryToolPart }) {
  return (
    <Tool className="mb-0 w-full">
      <ToolHeader state={part.state} title={title(part)} type="tool-query" />
      <ToolContent>
        {part.state === 'output-available' ? (
          <Result hints={part.input?.hints} output={part.output} />
        ) : (
          <>
            <Section label="Request">
              <p className="text-sm">{part.input?.request ?? 'Writing the query...'}</p>
            </Section>
            {part.state === 'output-error' && <ErrorSection message={part.errorText} />}
          </>
        )}
      </ToolContent>
    </Tool>
  )
}
