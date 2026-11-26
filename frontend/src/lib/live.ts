/**
 * "Casi en tiempo real": mientras la pantalla está a la vista, se pregunta cada 15 s si hay
 * novedades, y apenas se vuelve a la app. Con la app cerrada o en segundo plano no se pregunta
 * nada (React Query no refresca en segundo plano), así el servidor gratuito puede dormir.
 */
export const LIVE = { refetchInterval: 15_000, refetchOnWindowFocus: true } as const;
