import { PasskeySettings } from "@/features/account/passkey-settings";
import { PushSettings } from "@/features/account/push-settings";

export const metadata = { title: "Mi cuenta" };

export default function AccountPage() {
  return (
    <div className="flex flex-col gap-10">
      <PushSettings />
      <PasskeySettings />
    </div>
  );
}
