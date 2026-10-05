import { RequestPasswordReset } from "@/features/auth/password-reset";

export const metadata = { title: "Recuperar contraseña" };

export default function ResetPasswordPage() {
  return <RequestPasswordReset />;
}
