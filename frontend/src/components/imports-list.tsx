import { useQuery } from '@tanstack/react-query'
import { FileSpreadsheetIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { importsQuery } from '@/lib/api'
import { formatDateTime } from '@/lib/format'

export function ImportsList() {
  const { data: imports } = useQuery(importsQuery)

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
                  <TableCell className="max-w-[16rem] truncate font-medium" title={record.file_name}>
                    {record.file_name}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{record.account_name}</TableCell>
                  <TableCell>
                    <Badge variant={record.preset ? 'secondary' : 'outline'}>{record.preset ?? 'custom'}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{record.row_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{record.imported_count}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
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
