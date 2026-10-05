import type { components } from "./schema";

export type Schemas = components["schemas"];
export type Me = Schemas["MeResponse"];
export type Role = Schemas["Role"];
export type Member = Schemas["MemberOut"];
export type Invitation = Schemas["InvitationOut"];
export type Organization = Schemas["OrganizationOut"];
export type AuditLog = Schemas["AuditLogOut"];
