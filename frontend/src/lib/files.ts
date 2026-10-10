/** Archivos que se suben a la API (planillas, comprobantes, OC). */

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

/** El contenido en base64 (la API recibe los archivos así, dentro del JSON). */
export async function toBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

const MAX_SIDE = 2000;
const RESIZABLE = ["image/jpeg", "image/png", "image/webp"];

/**
 * Una foto del celular pesa 3–6 MB: se achica a 2000 px de lado en JPEG antes de subirla (en
 * campo la señal es mala). Si el navegador no puede, o no conviene, se sube el original.
 */
export async function shrinkImage(file: File): Promise<Blob> {
  if (!RESIZABLE.includes(file.type) || file.size < 600 * 1024) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext("2d");
    if (!context) return file;
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
    return blob && blob.size < file.size ? blob : file;
  } catch {
    return file;
  }
}

/** "ticket.png" achicado a JPEG se sube como "ticket.jpg". */
export function uploadName(name: string, blob: Blob): string {
  return blob.type === "image/jpeg" && !/\.jpe?g$/i.test(name) ? `${name.replace(/\.[^.]*$/, "")}.jpg` : name;
}

/** "1,5 MB" / "320 KB". */
export function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
