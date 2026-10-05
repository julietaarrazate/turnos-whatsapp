export const metadata = { title: "Sin conexión" };

export default function OfflinePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-2 p-6 text-center">
      <h1 className="text-xl font-semibold">Sin conexión</h1>
      <p className="text-ink-muted">
        No hay internet en este momento. Cuando vuelva la señal, recargá la página.
      </p>
    </main>
  );
}
