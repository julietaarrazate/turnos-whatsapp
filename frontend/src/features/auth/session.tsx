"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext } from "react";

import { api, unwrap } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";

/** Permisos tal como los define el backend (app/core/permissions.py). */
export type Permission =
  | "org.view"
  | "org.settings.manage"
  | "org.fiscal.manage"
  | "members.view"
  | "members.manage"
  | "audit.view"
  | "dashboard.view"
  | "cost.view"
  | "margin.view"
  | "clients.edit"
  | "catalog.edit"
  | "costs.edit"
  | "pricing.settings"
  | "budget.edit"
  | "budget.markup_override"
  | "proposal.send"
  | "proposal.decide"
  | "production.manage"
  | "expenses.edit"
  | "event.close"
  | "work.own";

export const ME_QUERY_KEY = ["auth", "me"] as const;

interface SessionValue {
  me: Me;
  can: (permission: Permission) => boolean;
  switchOrganization: (organizationId: string) => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function useMeQuery() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/auth/me")),
    staleTime: 60_000,
  });
}

export function SessionProvider({ me, children }: { me: Me; children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const router = useRouter();

  const can = useCallback((permission: Permission) => me.permissions.includes(permission), [me]);

  const switchOrganization = useCallback(
    async (organizationId: string) => {
      const next = unwrap(
        await api.POST("/api/v1/auth/switch-organization", {
          body: { organization_id: organizationId },
        }),
      );
      queryClient.clear();
      queryClient.setQueryData(ME_QUERY_KEY, next);
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    await api.POST("/api/v1/auth/logout");
    queryClient.clear();
    router.replace("/login");
  }, [queryClient, router]);

  return (
    <SessionContext.Provider value={{ me, can, switchOrganization, logout }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession fuera de SessionProvider");
  return value;
}
