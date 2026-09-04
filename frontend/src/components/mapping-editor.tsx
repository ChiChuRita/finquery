import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DATE_FORMATS, type CsvMapping, type DateFormat } from '@/lib/api'
import { cn } from '@/lib/utils'

const NONE = '__none__'

function ColumnSelect({
  id,
  label,
  columns,
  value,
  optional,
  onChange,
}: {
  id: string
  label: string
  columns: string[]
  value: string | null | undefined
  optional?: boolean
  onChange: (value: string | null) => void
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-muted-foreground text-xs" htmlFor={id}>
        {label}
      </Label>
      <Select onValueChange={(next) => onChange(next === NONE ? null : next)} value={value ?? NONE}>
        <SelectTrigger className="w-full" id={id} size="sm">
          <SelectValue placeholder="Pick a column" />
        </SelectTrigger>
        <SelectContent>
          {optional && <SelectItem value={NONE}>Not in this file</SelectItem>}
          {columns.map((column) => (
            <SelectItem key={column} value={column}>
              {column}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export function MappingEditor({
  header,
  mapping,
  onChange,
}: {
  header: string[]
  mapping: CsvMapping
  onChange: (mapping: CsvMapping) => void
}) {
  // Duplicate or blank header cells exist in the wild (ING repeats "Währung"); a select needs
  // one option per distinct value.
  const columns = [...new Set(header.filter((name) => name.trim()))]
  const split = !mapping.amount_column
  const patch = (fields: Partial<CsvMapping>) => onChange({ ...mapping, ...fields })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground text-xs">Amount columns</span>
        <div className="flex rounded-md border p-0.5">
          {[
            { label: 'One signed column', active: !split },
            { label: 'Debit and credit', active: split },
          ].map((option) => (
            <button
              className={cn(
                'rounded-sm px-2.5 py-1 text-xs transition-colors',
                option.active ? 'bg-secondary font-medium text-secondary-foreground' : 'text-muted-foreground',
              )}
              key={option.label}
              onClick={() =>
                patch(
                  option.label === 'One signed column'
                    ? { amount_column: columns[0] ?? null, debit_column: null, credit_column: null }
                    : { amount_column: null, debit_column: columns[0] ?? null, credit_column: columns[1] ?? null },
                )
              }
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <ColumnSelect
          columns={columns}
          id="map-date"
          label="Booking date"
          onChange={(value) => value && patch({ date_column: value })}
          value={mapping.date_column}
        />
        {split ? (
          <>
            <ColumnSelect
              columns={columns}
              id="map-debit"
              label="Debit (money out)"
              onChange={(value) => patch({ debit_column: value })}
              optional
              value={mapping.debit_column}
            />
            <ColumnSelect
              columns={columns}
              id="map-credit"
              label="Credit (money in)"
              onChange={(value) => patch({ credit_column: value })}
              optional
              value={mapping.credit_column}
            />
          </>
        ) : (
          <ColumnSelect
            columns={columns}
            id="map-amount"
            label="Amount"
            onChange={(value) => value && patch({ amount_column: value })}
            value={mapping.amount_column}
          />
        )}
        <ColumnSelect
          columns={columns}
          id="map-description"
          label="Description"
          onChange={(value) => patch({ description_column: value })}
          optional
          value={mapping.description_column}
        />
        <ColumnSelect
          columns={columns}
          id="map-counterparty"
          label="Counterparty"
          onChange={(value) => patch({ counterparty_column: value })}
          optional
          value={mapping.counterparty_column}
        />
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs" htmlFor="map-date-format">
            Date format
          </Label>
          <Select
            onValueChange={(next) => patch({ date_format: next as DateFormat })}
            value={mapping.date_format}
          >
            <SelectTrigger className="w-full" id="map-date-format" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DATE_FORMATS.map((format) => (
                <SelectItem key={format} value={format}>
                  {format}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs" htmlFor="map-decimal">
            Decimal separator
          </Label>
          <Select
            onValueChange={(next) => patch({ decimal_separator: next as CsvMapping['decimal_separator'] })}
            value={mapping.decimal_separator}
          >
            <SelectTrigger className="w-full" id="map-decimal" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="comma">Comma (1.234,56)</SelectItem>
              <SelectItem value="dot">Dot (1,234.56)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  )
}
