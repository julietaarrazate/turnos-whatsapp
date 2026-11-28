/** "iPhone · Safari", "Android · Chrome", "Mac · Chrome"... a partir del user agent de la sesión. */
export function describeDevice(userAgent: string | null | undefined): string {
  if (!userAgent) return "Dispositivo desconocido";
  const ua = userAgent;
  const system = /iPhone/.test(ua)
    ? "iPhone"
    : /iPad/.test(ua)
      ? "iPad"
      : /Android/.test(ua)
        ? "Android"
        : /Windows/.test(ua)
          ? "Windows"
          : /Macintosh|Mac OS X/.test(ua)
            ? "Mac"
            : /Linux/.test(ua)
              ? "Linux"
              : null;
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /SamsungBrowser/.test(ua)
      ? "Samsung Internet"
      : /CriOS|Chrome\//.test(ua)
        ? "Chrome"
        : /FxiOS|Firefox\//.test(ua)
          ? "Firefox"
          : /Safari\//.test(ua)
            ? "Safari"
            : null;
  const parts = [system, browser].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Dispositivo desconocido";
}

/** "hace 5 min", "hace 3 h", "hace 2 días". */
export function timeAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "nunca";
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "recién";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.round(hours / 24);
  return days === 1 ? "hace 1 día" : `hace ${days} días`;
}
