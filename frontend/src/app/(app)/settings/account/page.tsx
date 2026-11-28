import { PasskeySettings } from "@/features/account/passkey-settings";
import { PasswordForm, PinSettings, ProfileForm } from "@/features/account/profile-settings";
import { PushSettings } from "@/features/account/push-settings";

export const metadata = { title: "Mi perfil" };

export default function AccountPage() {
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">Mi perfil</h1>
      <ProfileForm />
      <PasswordForm />
      <PinSettings />
      <div className="max-w-xl rounded-xl border border-line bg-surface p-5">
        <PasskeySettings />
      </div>
      <div className="max-w-xl rounded-xl border border-line bg-surface p-5">
        <PushSettings />
      </div>
    </div>
  );
}
