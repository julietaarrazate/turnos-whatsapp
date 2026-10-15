"use client";

import { Copy, Send } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

/** Un link para pasar a mano: copiarlo o mandarlo por WhatsApp (wa.me con el mensaje armado). */
export function ShareLink({
  url,
  inputLabel,
  whatsappText,
  children,
}: {
  url: string;
  inputLabel: string;
  whatsappText: string;
  children?: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <>
      <input
        readOnly
        value={url}
        aria-label={inputLabel}
        onFocus={(e) => e.currentTarget.select()}
        className="h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm"
      />
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          onClick={() => {
            void navigator.clipboard?.writeText(url).then(() => setCopied(true));
          }}
        >
          <Copy className="size-4" aria-hidden /> {copied ? "¡Copiado!" : "Copiar link"}
        </Button>
        <a
          href={`https://wa.me/?text=${encodeURIComponent(whatsappText)}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-8 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-sm font-medium"
        >
          <Send className="size-4" aria-hidden /> WhatsApp
        </a>
        {children}
      </div>
    </>
  );
}
