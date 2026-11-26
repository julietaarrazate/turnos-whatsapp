"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useSession, type Permission } from "@/features/auth/session";
import { cn } from "@/lib/cn";

const TABS: { href: string; label: string; permission: Permission }[] = [
  { href: "/settings/organization", label: "Organización", permission: "org.view" },
  { href: "/settings/pricing", label: "Precios", permission: "margin.view" },
  { href: "/settings/members", label: "Usuarios y roles", permission: "members.view" },
  { href: "/settings/audit", label: "Auditoría", permission: "audit.view" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { can } = useSession();
  return (
    <>
      <nav aria-label="Configuración" className="-mx-4 mb-6 overflow-x-auto border-b border-line px-4 lg:mx-0 lg:px-0">
        <ul className="flex gap-1">
          {TABS.filter((tab) => can(tab.permission)).map((tab) => (
            <li key={tab.href}>
              <Link
                href={tab.href}
                aria-current={pathname === tab.href ? "page" : undefined}
                className={cn(
                  "inline-block border-b-2 px-3 py-2.5 text-sm whitespace-nowrap",
                  pathname === tab.href ? "border-accent font-medium text-ink" : "border-transparent text-ink-muted hover:text-ink",
                )}
              >
                {tab.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {children}
    </>
  );
}
