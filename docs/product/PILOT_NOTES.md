# Notas de la piloto

Lo que aprendimos del material real de la productora piloto. Se describe la **estructura**, no
los importes ni los datos de sus clientes.

## Planilla de presupuesto (Excel, octubre 2026)

Una hoja por evento con dos mitades:

- **Izquierda, "ppto venta"** (lo que ve el cliente): rubros (Locación, Producción y proyecto,
  Zona…, Varios de producción, Merch, Cobertura, Traslados, RRHH, Seguros y permisos) y, en cada
  uno, ítems con *detalle*, cantidad, jornadas, precio unitario y precio total
  (`Q × jornadas × unitario`). Los totales se ven **más IVA**.
- **Derecha, "META"** (interna): proveedor / observaciones (a veces con una descripción distinta
  de la del cliente), costo unitario, costo total, utilidad por línea, **Nº de factura** y
  **condición de pago**. Colores por fila: *proveedor cotizado*, *factura cargada*, *pagado*.

### Cómo calcula

- **Fija el precio de venta por línea** (no costo × markup): el markup resultante va de ~8 % a
  casi 200 % según el ítem. → El editor ya permite precio objetivo por línea; conviene que sea
  el modo cómodo por defecto para esta productora.
- Muchas veces carga el **costo total de la línea** (lo que cotizó el proveedor por todo), no
  un costo unitario. → Falta un modo "costo total" en la línea.
- Líneas **"Bonificado"** (se muestran al cliente sin cargo) y **"A definir" / TBD** (sin
  precio todavía). → Falta una etiqueta de precio para la propuesta en vez de mostrar $ 0.
- **Fee de gestión** como porcentaje sobre el subtotal, visible al cliente. → Falta un
  recargo porcentual a nivel versión.
- **Costo impositivo** interno sobre la venta (no se le cobra al cliente). → Ya cubierto por los
  cargos sobre la venta.
- Validez 7 días y condición de pago en notas al pie. → Ya cubierto (vigencia y forma de pago).

### Qué cambió en el producto por esto

- 4.2: la lista de contratación sigue sus estados (cotizado → confirmado → factura cargada →
  pagado) con Nº de factura y condición de pago.

### Pendiente (próximos PR)

1. Línea: modo **costo total**; etiqueta **Bonificado / A definir** en la propuesta.
2. Versión: **fee de gestión %** visible al cliente.
3. **Importar un presupuesto** desde esta planilla (rubros → secciones, ítems → líneas, META →
   costos y proveedores), para migrar los eventos que ya tiene.
