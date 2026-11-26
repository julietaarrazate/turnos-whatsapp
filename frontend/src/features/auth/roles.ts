import type { Role } from "@/lib/api/types";

export const ROLE_LABELS: Record<Role, string> = {
  OWNER: "Dueño/a",
  ADMIN: "Administración",
  MANAGER: "Gerencia",
  QUOTER: "Comercial",
  PRODUCTION: "Producción",
  VIEWER: "Solo lectura",
  CREW: "Taller/Montaje",
};

export const ROLE_OPTIONS = (Object.keys(ROLE_LABELS) as Role[]).map((value) => ({
  value,
  label: ROLE_LABELS[value],
}));
