import {
  WebAuthnAbortService,
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";

import { api, unwrap } from "@/lib/api/client";

/** Marcas locales de este dispositivo (no son secretas: la llave vive en el teléfono). */
const HERE = "passkey-here";
const DECLINED = "passkey-declined";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // modo privado: no pasa nada, solo no se recuerda
  }
}

export const passkeyHere = () => read(HERE) === "1";
export const passkeyDeclined = () => read(DECLINED) === "1";
export const declinePasskey = () => write(DECLINED, "1");
export const forgetPasskeyHere = () => write(HERE, null);

/** ¿Este dispositivo tiene huella, cara o bloqueo de pantalla que sirva para entrar? */
export async function passkeysAvailable(): Promise<boolean> {
  if (!browserSupportsWebAuthn()) return false;
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

/** La persona canceló o cerró el cartel del teléfono: no es un error para mostrar. */
export function wasCancelled(error: unknown): boolean {
  return error instanceof Error && (error.name === "NotAllowedError" || error.name === "AbortError");
}

export async function registerPasskey() {
  const optionsJSON = unwrap(await api.POST("/api/v1/auth/passkeys/register/options"));
  // El servidor arma las opciones con la misma forma (py_webauthn → JSON estándar).
  const credential = await startRegistration({
    optionsJSON: optionsJSON as unknown as PublicKeyCredentialCreationOptionsJSON,
  });
  const created = unwrap(await api.POST("/api/v1/auth/passkeys", { body: { credential: { ...credential } } }));
  write(HERE, "1");
  return created;
}

export async function loginWithPasskey() {
  WebAuthnAbortService.cancelCeremony();
  const optionsJSON = unwrap(await api.POST("/api/v1/auth/passkeys/login/options"));
  const credential = await startAuthentication({
    optionsJSON: optionsJSON as unknown as PublicKeyCredentialRequestOptionsJSON,
  });
  const me = unwrap(await api.POST("/api/v1/auth/passkeys/login", { body: { credential: { ...credential } } }));
  write(HERE, "1");
  return me;
}
