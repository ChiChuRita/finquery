import { useQuery } from '@tanstack/react-query'
import { AlertTriangleIcon, FileSpreadsheetIcon, ScaleIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { importsQuery, type ImportRecord } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/lib/workspace'

const waitingOn = (record: ImportRecord) =>
  record.duplicate_count - record.duplicates_kept - record.duplicates_removed

/** The column counts candidates; what became of them is the tooltip, and the decisions are it. */
function duplicateNote(record: ImportRecord): string {
  if (record.duplicate_count === 0) return 'No booking of this file was already in the profile'
  const waiting = waitingOn(record)
  return (
    `${record.duplicates_kept} kept, ${record.duplicates_removed} removed` +
    (waiting > 0 ? `, ${waiting} still waiting for your decision` : '')
  )
}

export function ImportsList() {
  const { profile } = useWorkspace()
  const { data: imports } = useQuery(importsQuery(profile?.id))

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-heading font-semibold text-sm">Past imports</h2>
        {imports && imports.length > 0 && (
          <span className="text-muted-foreground text-xs">{imports.length} in this profile</span>
        )}
      </div>

      {!imports || imports.length === 0 ? (
        <div className="flex items-center gap-3 rounded-xl border border-dashed px-4 py-6 text-muted-foreground text-sm">
          <FileSpreadsheetIcon className="size-4 shrink-0" />
          Nothing imported yet. Every import you commit is listed here with its row counts.
        </div>
      ) : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Account</TableHead>
                <TableHead>Mapping</TableHead>
                <TableHead className="text-right">Rows</TableHead>
                <TableHead className="text-right">Imported</TableHead>
                <TableHead className="text-right">Duplicates</TableHead>
                <TableHead className="text-right">When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {imports.map((record) => (
                <TableRow key={record.id}>
                  {/* Seven columns need more room than 1024 wide gives, so the two text columns
                      give way first: a truncated file name that carries its full name in the
                      title beats a "When" column cut down to a "W". */}
                  <TableCell className="max-w-[9rem] truncate font-medium xl:max-w-[13rem]" title={record.file_name}>
                    <span className="flex items-center gap-1.5">
                      {/* Only an extraction has a reconciliation verdict, and the icon carries it:
                          seven columns have no room for the sentence, and the title does. */}
                      {record.reconciliation &&
                        (record.reconciliation.startsWith('Reconciled') ? (
                          <ScaleIcon aria-hidden="true" className="size-3.5 shrink-0 text-primary" />
                        ) : (
                          <AlertTriangleIcon
                            aria-hidden="true"
                            className="size-3.5 shrink-0 text-amber-600 dark:text-amber-500"
                          />
                        ))}
                      <span className="truncate" title={record.reconciliation ?? record.file_name}>
                        {record.file_name}
                      </span>
                    </span>
                  </TableCell>
                  <TableCell
                    className="max-w-[9rem] truncate text-muted-foreground xl:max-w-[12rem]"
                    title={record.account_name}
                  >
                    {record.account_name}
                  </TableCell>
                  <TableCell>
                    <Badge variant={record.preset ? 'secondary' : 'outline'}>{record.preset ?? 'custom'}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{record.row_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{record.imported_count}</TableCell>
                  <TableCell
                    className={cn(
                      'text-right tabular-nums',
                      waitingOn(record) > 0
                        ? 'font-medium text-amber-600 dark:text-amber-500'
                        : 'text-muted-foreground',
                    )}
                    title={duplicateNote(record)}
                  >
                    {record.duplicate_count}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-right text-muted-foreground text-xs">
                    {formatDateTime(record.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}
