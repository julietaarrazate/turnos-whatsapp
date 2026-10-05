import { AcceptInvitation } from "@/features/auth/accept-invitation";

export const metadata = { title: "Invitación" };

export default async function InvitePage(props: PageProps<"/invite/[token]">) {
  const { token } = await props.params;
  return <AcceptInvitation token={token} />;
}
