"use client";

import { useMutation } from "@tanstack/react-query";
import { Bell, BellOff } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";

import { currentSubscription, disablePush, enablePush, pushSupport } from "./push";

/** "Avisos en este teléfono": lo mismo que la campanita, aunque la app esté cerrada. */
export function PushSettings() {
  const [support, setSupport] = useState<ReturnType<typeof pushSupport>>("no");
  const [on, setOn] = useState(false);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    void currentSubscription().then((subscription) => {
      setSupport(pushSupport());
      setOn(Boolean(subscription));
      setDenied(typeof Notification !== "undefined" && Notification.permission === "denied");
    });
  }, []);

  const toggle = useMutation({
    mutationFn: async () => {
      if (on) {
        await disablePush();
        return false;
      }
      const result = await enablePush();
      if (result === "denied") {
        setDenied(true);
        return false;
      }
      return true;
    },
    onSuccess: setOn,
  });
  const test = useMutation({ mutationFn: async () => unwrap(await api.POST("/api/v1/push/test")) });

  return (
    <section aria-labelledby="push-title" className="flex max-w-xl flex-col gap-3">
      <div>
        <h2 id="push-title" className="text-lg font-semibold">
          Avisos en este teléfono
        </h2>
        <p className="text-sm text-ink-muted">
          Te avisa cuando suben un avance, cambia una pieza de fase o el cliente responde un diseño, aunque tengas la app cerrada. Lo que
          hacés vos no te avisa.
        </p>
      </div>
      {support === "install-ios" ? (
        <Notice tone="info">
          En iPhone, primero agregá Handie a la pantalla de inicio (botón Compartir → “Agregar a inicio”) y abrila desde ahí.
        </Notice>
      ) : support === "no" ? (
        <p className="text-sm text-ink-muted">Este navegador no permite avisos.</p>
      ) : denied && !on ? (
        <Notice tone="warning">
          Bloqueaste los avisos para Handie. Habilitalos en la configuración del navegador (el candado al lado de la dirección) y volvé a
          intentar.
        </Notice>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant={on ? "secondary" : "primary"} loading={toggle.isPending} onClick={() => toggle.mutate()}>
            {on ? <BellOff className="size-4" aria-hidden /> : <Bell className="size-4" aria-hidden />}
            {on ? "Apagar avisos en este teléfono" : "Activar avisos en este teléfono"}
          </Button>
          {on ? (
            <Button variant="ghost" loading={test.isPending} onClick={() => test.mutate()}>
              Mandarme uno de prueba
            </Button>
          ) : null}
        </div>
      )}
      {on ? <p className="text-sm text-success">Activados en este teléfono.</p> : null}
      {toggle.isError ? <Notice tone="error">{errorMessage(toggle.error)}</Notice> : null}
      {test.isError ? <Notice tone="error">{errorMessage(test.error)}</Notice> : null}
    </section>
  );
}
