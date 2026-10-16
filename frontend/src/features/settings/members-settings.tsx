"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { ShareLink } from "@/components/ui/share-link";
import { ROLE_LABELS, ROLE_OPTIONS } from "@/features/auth/roles";
import { useSession } from "@/features/auth/session";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/format/date";
import type { Member, Role, Schemas } from "@/lib/api/types";

const MEMBERS_KEY = ["members"] as const;
const INVITATIONS_KEY = ["invitations"] as const;

function MemberRow({ member, canManage, isSelf, isOwner }: { member: Member; canManage: boolean; isSelf: boolean; isOwner: boolean }) {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: async (body: { role?: Role; status?: "ACTIVE" | "DISABLED" }) =>
      unwrap(
        await api.PATCH("/api/v1/members/{membership_id}", {
          params: { path: { membership_id: member.membership_id } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MEMBERS_KEY }),
  });
  const disabled = member.status === "DISABLED";
  // Solo un OWNER asigna o modifica OWNERs (la regla real vive en el servidor).
  const roleOptions = isOwner ? ROLE_OPTIONS : ROLE_OPTIONS.filter((o) => o.value !== "OWNER");
  const editable = canManage && (isOwner || member.role !== "OWNER");

  return (
    <li className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className={disabled ? "font-medium text-ink-muted line-through" : "font-medium"}>
          {member.name} {isSelf ? <span className="text-xs font-normal text-ink-muted">(vos)</span> : null}
        </p>
        {member.email ? <p className="truncate text-sm text-ink-muted">{member.email}</p> : null}
        {update.isError ? <p className="mt-1 text-sm text-danger">{errorMessage(update.error)}</p> : null}
      </div>
      {editable ? (
        <div className="flex items-center gap-2">
          <select
            aria-label={`Rol de ${member.name}`}
            value={member.role}
            disabled={update.isPending}
            onChange={(event) => update.mutate({ role: event.target.value as Role })}
            className="h-10 rounded-lg border border-line bg-surface px-2 text-sm"
          >
            {roleOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {!isSelf ? (
            <Button
              variant="ghost"
              size="sm"
              loading={update.isPending}
              onClick={() => update.mutate({ status: disabled ? "ACTIVE" : "DISABLED" })}
            >
              {disabled ? "Reactivar" : "Desactivar"}
            </Button>
          ) : null}
        </div>
      ) : (
        <span className="text-sm text-ink-muted">{ROLE_LABELS[member.role]}</span>
      )}
    </li>
  );
}

/** El link de la invitación, para mandarlo a mano (sin email configurado, es la única forma). */
function InviteShare({ invitation, organization }: { invitation: Schemas["InvitationCreated"]; organization: string }) {
  const url = typeof window === "undefined" ? invitation.invite_path : `${window.location.origin}${invitation.invite_path}`;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-success/30 bg-success/10 p-4">
      <p className="text-sm font-medium">
        {invitation.emailed
          ? `Invitación enviada por email a ${invitation.email}. También podés mandarle el link:`
          : `Invitación creada para ${invitation.email}. Mandale este link:`}
      </p>
      <ShareLink
        url={url}
        inputLabel="Link de la invitación"
        whatsappText={`Hola! Te invité a sumarte a ${organization}. Entrá a este link para crear tu cuenta: ${url}`}
      />
      <p className="text-xs text-ink-muted">
        Vence el {formatDate(invitation.expires_at)} y sirve una sola vez. Por seguridad se muestra solo ahora: si lo perdés,
        invitá de nuevo al mismo email (el anterior deja de funcionar).
      </p>
    </div>
  );
}

function InviteForm() {
  const queryClient = useQueryClient();
  const { me } = useSession();
  const [created, setCreated] = useState<Schemas["InvitationCreated"] | null>(null);
  const invite = useMutation({
    mutationFn: async (body: { email: string; role: Role }) => unwrap(await api.POST("/api/v1/invitations", { body })),
    onSuccess: (data) => {
      setCreated(data);
      void queryClient.invalidateQueries({ queryKey: INVITATIONS_KEY });
    },
  });
  const organization = me.memberships.find((m) => m.organization_id === me.active_organization_id)?.organization_name ?? "la productora";
  const options = me.role === "OWNER" ? ROLE_OPTIONS : ROLE_OPTIONS.filter((o) => o.value !== "OWNER");

  return (
    <form
      className="grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setCreated(null);
        invite.mutate(
          { email: String(form.get("email")), role: String(form.get("role")) as Role },
          { onSuccess: () => (event.target as HTMLFormElement).reset() },
        );
      }}
    >
      <TextField label="Email" name="email" type="email" inputMode="email" required />
      <SelectField label="Rol" name="role" defaultValue="QUOTER" options={options} />
      <Button type="submit" loading={invite.isPending}>
        Invitar
      </Button>
      {invite.isError ? (
        <div className="sm:col-span-3">
          <Notice tone="error">{errorMessage(invite.error)}</Notice>
        </div>
      ) : null}
      {created ? (
        <div className="sm:col-span-3">
          <InviteShare invitation={created} organization={organization} />
        </div>
      ) : null}
    </form>
  );
}

function PendingInvitations() {
  const queryClient = useQueryClient();
  const invitations = useQuery({
    queryKey: INVITATIONS_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/invitations")),
  });
  const revoke = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE("/api/v1/invitations/{invitation_id}", { params: { path: { invitation_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INVITATIONS_KEY }),
  });
  if (!invitations.data?.length) return null;
  return (
    <ul className="mt-4 divide-y divide-line border-t border-line">
      {invitations.data.map((invitation) => (
        <li key={invitation.id} className="flex items-center gap-3 py-3 text-sm">
          <div className="min-w-0 flex-1">
            <p className="truncate">{invitation.email}</p>
            <p className="text-ink-muted">
              {ROLE_LABELS[invitation.role]} · vence {formatDate(invitation.expires_at)}
            </p>
          </div>
          <Button variant="ghost" size="sm" loading={revoke.isPending} onClick={() => revoke.mutate(invitation.id)}>
            Anular
          </Button>
        </li>
      ))}
    </ul>
  );
}

export function MembersSettings() {
  const { me, can } = useSession();
  const members = useQuery({
    queryKey: MEMBERS_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/members")),
  });
  const canManage = can("members.manage");

  return (
    <>
      <PageHeader title="Usuarios y roles" description="Quién trabaja en la organización y qué puede hacer." />
      <div className="flex flex-col gap-4">
        {canManage ? (
          <section className="rounded-xl border border-line bg-surface p-5">
            <h2 className="mb-4 font-semibold">Invitar a alguien</h2>
            <InviteForm />
            <PendingInvitations />
          </section>
        ) : null}
        <section className="rounded-xl border border-line bg-surface px-5">
          {members.isPending ? <p className="py-4 text-sm text-ink-muted">Cargando…</p> : null}
          {members.isError ? (
            <div className="py-4">
              <Notice tone="error">{errorMessage(members.error)}</Notice>
            </div>
          ) : null}
          <ul className="divide-y divide-line">
            {members.data?.map((member) => (
              <MemberRow
                key={member.membership_id}
                member={member}
                canManage={canManage}
                isSelf={member.user_id === me.user.id}
                isOwner={me.role === "OWNER"}
              />
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
