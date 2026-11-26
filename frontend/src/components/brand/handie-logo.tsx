import { cn } from "@/lib/cn";

/** Un handy (walkie-talkie). `mirror` pone la antena del otro lado. */
function Handy({ body, mirror = false }: { body: string; mirror?: boolean }) {
  return (
    <g transform={mirror ? "scale(-1,1)" : undefined}>
      <rect x="-40" y="-176" width="18" height="76" rx="9" className={body} />
      <rect x="20" y="-124" width="22" height="20" rx="6" className={body} />
      <rect x="-62" y="-112" width="124" height="236" rx="30" className={body} />
      <rect x="-38" y="-84" width="76" height="46" rx="10" className="fill-surface" />
      {[-2, 24, 50].map((y) => (
        <line key={y} x1="-32" y1={y} x2="32" y2={y} className="stroke-surface" strokeWidth="11" strokeLinecap="round" />
      ))}
      <circle cx="0" cy="88" r="9" className="fill-surface" />
    </g>
  );
}

/** Símbolo de Handie: dos handies con señal entre las antenas. Toma los colores del tema. */
export function HandieMark({ className }: { className?: string }) {
  return (
    <svg viewBox="56 36 400 424" aria-hidden className={className}>
      <g transform="translate(160 316) rotate(9)">
        <Handy body="fill-brand" mirror />
      </g>
      <g transform="translate(352 316) rotate(-9)">
        <Handy body="fill-magenta" />
      </g>
      <g fill="none" className="stroke-magenta" strokeWidth="12" strokeLinecap="round" transform="translate(0 -10)">
        <circle cx="256" cy="104" r="11" className="fill-magenta stroke-none" />
        <path d="M 234 82 A 31 31 0 0 0 234 126" />
        <path d="M 278 82 A 31 31 0 0 1 278 126" />
        <path d="M 214 64 A 57 57 0 0 0 214 144" opacity=".6" />
        <path d="M 298 64 A 57 57 0 0 1 298 144" opacity=".6" />
      </g>
    </svg>
  );
}

/** Logo con nombre: símbolo + "handie." */
export function HandieLogo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <HandieMark className="size-12" />
      <span aria-hidden className="text-2xl font-extrabold tracking-tight text-ink">
        handie<span className="text-magenta">.</span>
      </span>
      <span className="sr-only">Handie</span>
    </span>
  );
}
