import {
  BarChart3,
  Building2,
  CalendarDays,
  FileText,
  Home,
  Package,
  Settings,
  Truck,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Fase del plan en la que se construye (MVP.md). Sin fase = disponible. */
  phase?: number;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Inicio", icon: Home },
  { href: "/events", label: "Eventos", icon: CalendarDays, phase: 2 },
  { href: "/budgets", label: "Presupuestos", icon: FileText, phase: 2 },
  { href: "/catalog", label: "Catálogo", icon: Package },
  { href: "/clients", label: "Clientes", icon: Building2 },
  { href: "/suppliers", label: "Proveedores", icon: Truck },
  { href: "/reports", label: "Reportes", icon: BarChart3, phase: 5 },
  { href: "/settings", label: "Configuración", icon: Settings },
];

/** Barra inferior en mobile: 4 destinos + el botón central "+". */
export const MOBILE_TABS = ["/", "/events", "/budgets"] as const;

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
