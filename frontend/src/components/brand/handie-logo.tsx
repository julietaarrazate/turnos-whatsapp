import { cn } from "@/lib/cn";

/** Un handy parado: antena afuera, cuerpo y pantalla. Dos de estos forman la "H". */
function Handy({ x, antennaLeft, side }: { x: number; antennaLeft: boolean; side: "l" | "r" }) {
  return (
    <g className={`handie-${side}`}>
      <rect className="handie-ant" x={antennaLeft ? x + 14 : x + 70} y="86" width="24" height="110" rx="12" />
      <rect x={x} y="164" width="108" height="248" rx="36" />
      <rect className="handie-screen fill-surface" x={x + 22} y="192" width="64" height="46" rx="11" />
    </g>
  );
}

/**
 * Isotipo de Handie: una "H" hecha con dos handies que se pasan un mensaje (los tres puntos de
 * "escribiendo…"). En chico los puntos forman la barra de la H. Toma los colores del tema.
 * `animated`: entran los handies, suben las antenas y los puntos viajan (respeta "reducir movimiento").
 */
export function HandieMark({ className, animated = false }: { className?: string; animated?: boolean }) {
  return (
    <svg viewBox="80 70 352 360" aria-hidden className={cn(animated && "handie-animated", "overflow-visible", className)}>
      <g className="fill-brand">
        <Handy x={100} antennaLeft side="l" />
      </g>
      <g className="fill-magenta">
        <Handy x={304} antennaLeft={false} side="r" />
      </g>
      <circle className="handie-dot handie-d0 fill-brand" cx="227" cy="300" r="19" />
      <circle className="handie-dot handie-d1 fill-magenta opacity-60" cx="256" cy="300" r="19" />
      <circle className="handie-dot handie-d2 fill-magenta" cx="285" cy="300" r="19" />
    </svg>
  );
}

/** Logo con nombre: isotipo + "handie." */
export function HandieLogo({ className, animated = false }: { className?: string; animated?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <HandieMark className="size-14" animated={animated} />
      <span aria-hidden className="text-3xl font-extrabold tracking-tight text-ink">
        handie<span className="text-magenta">.</span>
      </span>
      <span className="sr-only">Handie</span>
    </span>
  );
}
