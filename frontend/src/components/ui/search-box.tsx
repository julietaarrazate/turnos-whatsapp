import { Search } from "lucide-react";

export function SearchBox({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <div className="relative flex-1">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
      <input
        type="search"
        aria-label={label}
        placeholder={label}
        value={value}
        maxLength={100}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-base placeholder:text-ink-muted focus:border-accent focus:outline-2 focus:outline-accent/30 sm:h-10 sm:text-sm"
      />
    </div>
  );
}
