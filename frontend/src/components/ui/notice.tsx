import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "warning" | "error";

const tones: Record<Tone, string> = {
  info: "border-line bg-subtle text-ink",
  success: "border-success/30 bg-success/10 text-ink",
  warning: "border-warning/40 bg-warning/10 text-ink",
  error: "border-danger/30 bg-danger/10 text-danger",
};

export function Notice({ tone = "info", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("rounded-lg border px-3 py-2 text-sm", tones[tone])}>
      {children}
    </div>
  );
}
