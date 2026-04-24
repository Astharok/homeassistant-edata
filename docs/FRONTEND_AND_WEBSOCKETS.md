# Frontend y websockets

> Última actualización: 2026-04-24

## Tarjetas Lovelace

La integración registra automáticamente `edata-card.js` como recurso JS de Lovelace
versionado. Contiene dos custom elements independientes.

---

### `edata-card` — tarjeta general

#### Tecnologías

- `LitElement 4.1.1`
- `ApexCharts 5.3.3`
- `tinycolor2`

#### Plantillas de gráfica soportadas

| Plantilla | Descripción |
|---|---|
| `consumptions` | Consumo energético histórico |
| `surplus` | Excedente / vertido histórico |
| `maximeter` | Potencia máxima registrada |
| `costs` | Costes de facturación |
| `summary-last-day` | Resumen del último día |
| `summary-last-month` | Resumen del último mes |
| `summary-month` | Resumen del mes actual |

#### Agregaciones soportadas

`year`, `month`, `week`, `day`, `hour`

#### Configuración mínima

```yaml
type: custom:edata-card
entity: sensor.edata_XXXX
graph_type: consumptions
group_by: month
```

---

### `edata-solar-card` — panel solar

Tarjeta nueva (2026-04-24) para visualización de energía solar y facturación real.

#### Configuración mínima

```yaml
type: custom:edata-solar-card
entity: sensor.edata_XXXX
title: "Panel Solar"
```

#### Funcionalidades

| Elemento | Descripción |
|---|---|
| Selector ◀▶ | Navega entre meses del histórico |
| KPI chips | Importado, Producido, Autoconsumo, Vertido (kWh) |
| Donut A | Origen del consumo: red vs autoconsumo (valor kWh + %) |
| Donut B | Destino de producción: autoconsumo vs vertido (valor kWh + %) |
| Tabla factura | Potencia, Energía, Compensación, Contador, Total |
| Chip ahorro | Ahorro solar estimado en € |
| Barras kWh | 13 meses apilados: importado + autoconsumo + vertido |
| Barras € | 13 meses apilados por componente de factura |

Los donuts aparecen sólo si el sidecar tiene datos de generación para ese mes.
La tabla de factura aparece sólo si hay reglas de facturación configuradas.

#### Datos que consume

Llama a `edata/consumptions/monthly` (API v1 enriquecida).
Cada registro devuelto incluye:

```
datetime, value_kWh, surplus_kWh, value_p1_kWh, value_p2_kWh, value_p3_kWh,
generation_kWh, self_consumption_kWh,
energy_term, power_term, surplus_term, others_term, value_eur
```

---

## API websocket

### API v1 (legado — datos precalculados en memoria)

| Comando | Datos devueltos |
|---|---|
| `edata/consumptions/daily` | Lista diaria con `value_kWh`, `surplus_kWh` |
| `edata/consumptions/monthly` | Lista mensual enriquecida con solar + costes por término |
| `edata/maximeter` | Lista de registros de maxímetro |

### API v2 (actual — consulta a estadísticas)

| Comando | Parámetros opcionales | Datos devueltos |
|---|---|---|
| `edata/ws/consumptions` | `tariff` (p1/p2/p3) | Histórico de consumo agregado |
| `edata/ws/surplus` | — | Histórico de excedente |
| `edata/ws/costs` | `tariff` | Histórico de costes |
| `edata/ws/maximeter` | `tariff` (p1/p2) | Histórico de maxímetro |
| `edata/ws/summary` | — | Atributos resumen calculados por la librería |

### Contrato del endpoint mensual enriquecido

`edata/consumptions/monthly` pasa por `_enrich_monthly_with_sidecar()` antes
de devolverse. El enrichment agrega sidecar por ciclo de facturación y une
los términos de coste de `cost_monthly_sum`. La `edata-solar-card` depende de
este contrato; cualquier cambio debe mantener los campos documentados arriba.

---

## Riesgos y notas de mantenimiento

- La coexistencia de API v1 y v2 obliga a mantener compatibilidad si se refactoriza.
- El campo `scups` se extrae del `entity_id` de la tarjeta: `sensor.edata_XXXX` → `xxxx`.
- Para trabajo futuro sobre vertido por tarifa, hay que decidir si ampliar
  `edata/ws/surplus` con selector `tariff` o mantener sólo total.

> Última actualización: 2026-04-24

## Tarjetas Lovelace

La integración registra automáticamente `edata-card.js` como recurso JS de Lovelace
versionado. Contiene dos custom elements independientes.

---

### `edata-card` — tarjeta general

#### Tecnologías

- `LitElement 4.1.1`
- `ApexCharts 5.3.3`
- `tinycolor2`

#### Plantillas de gráfica soportadas

| Plantilla | Descripción |
|---|---|
| `consumptions` | Consumo energético histórico |
| `surplus` | Excedente / vertido histórico |
| `maximeter` | Potencia máxima registrada |
| `costs` | Costes de facturación |
| `summary-last-day` | Resumen del último día |
| `summary-last-month` | Resumen del último mes |
| `summary-month` | Resumen del mes actual |

#### Agregaciones soportadas

`year`, `month`, `week`, `day`, `hour`

#### Configuración mínima

```yaml
type: custom:edata-card
entity: sensor.edata_XXXX
graph_type: consumptions
group_by: month
```

---

### `edata-solar-card` — panel solar

Tarjeta nueva (2026-04-24) para visualización de energía solar y facturación real.

#### Configuración mínima

```yaml
type: custom:edata-solar-card
entity: sensor.edata_XXXX
title: "Panel Solar"
```

#### Funcionalidades

| Elemento | Descripción |
|---|---|
| Selector ◀▶ | Navega entre meses del histórico |
| KPI chips | Importado, Producido, Autoconsumo, Vertido (kWh) |
| Donut A | Origen del consumo: red vs autoconsumo (valor kWh + %) |
| Donut B | Destino de producción: autoconsumo vs vertido (valor kWh + %) |
| Tabla factura | Potencia, Energía, Compensación, Contador, Total |
| Chip ahorro | Ahorro solar estimado en € |
| Barras kWh | 13 meses apilados: importado + autoconsumo + vertido |
| Barras € | 13 meses apilados por componente de factura |

Los donuts aparecen sólo si el sidecar tiene datos de generación para ese mes.
La tabla de factura aparece sólo si hay reglas de facturación configuradas.

#### Datos que consume

Llama a `edata/consumptions/monthly` (API v1 enriquecida).
Cada registro devuelto incluye:

```
datetime, value_kWh, surplus_kWh, value_p1_kWh, value_p2_kWh, value_p3_kWh,
generation_kWh, self_consumption_kWh,
energy_term, power_term, surplus_term, others_term, value_eur
```

---

## API websocket

### API v1 (legado — datos precalculados en memoria)

| Comando | Datos devueltos |
|---|---|
| `edata/consumptions/daily` | Lista diaria con `value_kWh`, `surplus_kWh` |
| `edata/consumptions/monthly` | Lista mensual enriquecida con solar + costes por término |
| `edata/maximeter` | Lista de registros de maxímetro |

### API v2 (actual — consulta a estadísticas)

| Comando | Parámetros opcionales | Datos devueltos |
|---|---|---|
| `edata/ws/consumptions` | `tariff` (p1/p2/p3) | Histórico de consumo agregado |
| `edata/ws/surplus` | — | Histórico de excedente |
| `edata/ws/costs` | `tariff` | Histórico de costes |
| `edata/ws/maximeter` | `tariff` (p1/p2) | Histórico de maxímetro |
| `edata/ws/summary` | — | Atributos resumen calculados por la librería |

### Contrato del endpoint mensual enriquecido

`edata/consumptions/monthly` pasa por `_enrich_monthly_with_sidecar()` antes
de devolverse. El enrichment agrega sidecar por ciclo de facturación y une
los términos de coste de `cost_monthly_sum`. La `edata-solar-card` depende de
este contrato; cualquier cambio debe mantener los campos documentados arriba.

---

## Riesgos y notas de mantenimiento

- La coexistencia de API v1 y v2 obliga a mantener compatibilidad si se refactoriza.
- El campo `scups` se extrae del `entity_id` de la tarjeta: `sensor.edata_XXXX` → `xxxx`.
- Para trabajo futuro sobre vertido por tarifa, hay que decidir si ampliar
  `edata/ws/surplus` con selector `tariff` o mantener sólo total.

## Tarjeta `edata-card`

La tarjeta nativa vive en `custom_components/edata/www/edata-card.js` y se carga automáticamente desde `__init__.py`.

### Tecnologías usadas

- `LitElement`
- `ApexCharts`
- `tinycolor2`

### Plantillas de gráfica soportadas

- `consumptions`
- `surplus`
- `maximeter`
- `costs`
- `summary-last-day`
- `summary-last-month`
- `summary-month`

### Agregaciones soportadas por la tarjeta

- `year`
- `month`
- `week`
- `day`
- `hour`

### Contrato mínimo de configuración

La tarjeta espera una entidad cuyo id empiece por `sensor.edata`. A partir de esa entidad extrae el `scups` y llama a la API websocket del backend.

## API websocket

La integración expone dos familias de comandos.

### API antigua

- `edata/consumptions/daily`
- `edata/consumptions/monthly`
- `edata/maximeter`

Estas rutas devuelven datos precalculados guardados directamente en `hass.data`.

### API actual

- `edata/ws/consumptions`
- `edata/ws/surplus`
- `edata/ws/costs`
- `edata/ws/maximeter`
- `edata/ws/summary`

Esta segunda API es la superficie principal para evoluciones futuras.

## Semántica de cada comando

### `edata/ws/consumptions`

Permite consultar consumo agregado total o por tarifa (`p1`, `p2`, `p3`).

### `edata/ws/surplus`

Permite consultar excedente o vertido agregado. En el código actual no recibe tarifa, por lo que la exposición pública se centra en el excedente total.

### `edata/ws/costs`

Devuelve histórico de costes total o por tarifa.

### `edata/ws/maximeter`

Devuelve máximos de potencia, opcionalmente filtrados por tarifa `p1` o `p2`.

### `edata/ws/summary`

Devuelve el diccionario de atributos calculados por la librería `e-data` para construir tarjetas resumen.

## Contrato backend-frontend para excedentes

La tarjeta ya contempla visualización de `surplus` en dos formas:

- serie temporal mediante la plantilla `surplus`
- resumen con dato de excedente en tarjetas de tipo `summary-*`

Esto significa que el frontend está preparado para mostrar vertido si el backend y las estadísticas le suministran los valores esperados.

## Riesgos y notas de mantenimiento

- La coexistencia de API websocket antigua y nueva obliga a mantener compatibilidad si se refactoriza.
- El frontend contiene bastante lógica de presentación y selección de consultas; conviene validar cualquier cambio real con Home Assistant antes de darlo por bueno.
- Para trabajo futuro sobre vertido por franjas, habrá que decidir si ampliar `edata/ws/surplus` con `tariff` o si mantener sólo agregado total.