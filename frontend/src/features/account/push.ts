import { api, unwrap } from "@/lib/api/client";

/** ¿Este navegador puede recibir avisos? (En iPhone, solo con Handie agregada al inicio.) */
export function pushSupport(): "ok" | "install-ios" | "no" {
  if (typeof window === "undefined") return "no";
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const installed = window.matchMedia?.("(display-mode: standalone)").matches;
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return ios && !installed ? "install-ios" : "no";
  }
  return "ok";
}

/** La clave pública viene en base64url; el navegador la quiere en bytes. */
export function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  return (await navigator.serviceWorker.getRegistration("/")) ?? navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (pushSupport() !== "ok") return null;
  const reg = await navigator.serviceWorker.getRegistration("/");
  return reg ? reg.pushManager.getSubscription() : null;
}

/** Pide permiso, se suscribe con la clave del servidor y la registra. */
export async function enablePush(): Promise<"ok" | "denied"> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  const status = unwrap(await api.GET("/api/v1/push"));
  const reg = await registration();
  await navigator.serviceWorker.ready;
  const subscription =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(status.public_key) }));
  const json = subscription.toJSON();
  unwrap(
    await api.POST("/api/v1/push/subscriptions", {
      body: { endpoint: subscription.endpoint, keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" } },
    }),
  );
  return "ok";
}

export async function disablePush(): Promise<void> {
  const subscription = await currentSubscription();
  if (!subscription) return;
  unwrap(await api.POST("/api/v1/push/unsubscribe", { body: { endpoint: subscription.endpoint } }));
  await subscription.unsubscribe();
}
