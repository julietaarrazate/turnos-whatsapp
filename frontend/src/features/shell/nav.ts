import {
  Activity,
  BarChart3,
  Building2,
  CalendarDays,
  ClipboardCheck,
  FileText,
  Home,
  Package,
  Settings,
  Truck,
  type LucideIcon,
} from "lucide-react";

import type { Permission } from "@/features/auth/session";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Fase del plan en la que se construye (MVP.md). Sin fase = disponible. */
  phase?: number;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Inicio", icon: Home },
  { href: "/my-work", label: "Mis tareas", icon: ClipboardCheck },
  { href: "/activity", label: "Actividad", icon: Activity },
  { href: "/events", label: "Eventos", icon: CalendarDays },
  { href: "/budgets", label: "Presupuestos", icon: FileText },
  { href: "/catalog", label: "Catálogo", icon: Package },
  { href: "/clients", label: "Clientes", icon: Building2 },
  { href: "/suppliers", label: "Proveedores", icon: Truck },
  { href: "/reports", label: "Reportes", icon: BarChart3 },
  { href: "/settings", label: "Configuración", icon: Settings },
];

/**
 * Barra inferior en mobile: 2 destinos, el botón central y 2 destinos. Cambia según el rol:
 * producción tiene la cámara al medio, "Actividad" y "Mis tareas" (como la maqueta); lo comercial,
 * "+", "Presupuestos" y "Más" (la configuración y el resto de las secciones).
 */
export interface MobileBar {
  left: string[];
  right: string[];
  center: "camera" | "create";
}

export function mobileBar(can: (permission: Permission) => boolean): MobileBar {
  const field = can("production.manage") && !can("budget.edit");
  return field
    ? { left: ["/", "/events"], right: ["/activity", "/my-work"], center: "camera" }
    : { left: ["/", "/events"], right: ["/budgets", "/settings"], center: "create" };
}

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
