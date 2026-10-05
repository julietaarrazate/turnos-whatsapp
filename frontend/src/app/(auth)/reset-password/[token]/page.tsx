import { ConfirmPasswordReset } from "@/features/auth/password-reset";

export const metadata = { title: "Nueva contraseña" };

export default async function ConfirmResetPage(props: PageProps<"/reset-password/[token]">) {
  const { token } = await props.params;
  return <ConfirmPasswordReset token={token} />;
}
