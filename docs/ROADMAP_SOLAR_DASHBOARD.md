# Roadmap: Datos solares completos + Panel de facturación

> Estado: **PLANIFICACIÓN** — No implementar hasta autorización explícita.
> Última actualización: 2026-04-23

---

## Contexto y motivación

Datadis expone en su API cinco campos por hora de consumo:

| Campo API | Descripción |
|---|---|
| `consumptionKWh` | Energía importada de la red |
| `surplusEnergyKWh` | Energía vertida a la red |
| `generationEnergyKWh` | Producción solar total (autoconsumo + vertido) |
| `selfConsumptionEnergyKWh` | Solar consumido directamente en casa |
| `obtainMethod` | `"Real"` o `"Estimada"` |

La librería `edata` solo mapea `consumptionKWh` → `value_kWh` y `surplusEnergyKWh` → `surplus_kWh`. El resto se descarta.

### Balance energético verificado (marzo 2026)

```
Producción solar (generation):    440.13 kWh
  └─ Autoconsumo (self_cons):     247.31 kWh
  └─ Vertido a red (surplus):     192.81 kWh  ✅ coincide con surplus_kWh

Consumo total casa:
  Importado de red:               383.57 kWh
+ Autoconsumo:                    247.31 kWh
─────────────────────────────────────────────
Total (≈ Shelly):                 630.88 kWh  (Shelly: 618.77 → delta 2%)

Identidad comprobada:
  generation = selfConsumption + surplus → 440.13 == 440.13 ✅
```

---

## Bloque 1 — Estadísticas LTS para todos los campos de Datadis

### Objetivo

Exponer `generation_kWh` y `self_consumption_kWh` como estadísticas LTS en HA
para que el panel Energía pueda usarlos, y para que estén disponibles
para sensores, automatizaciones y dashboards.

### Persistencia actual (sidecar)

Los campos extra ya se almacenan en `edata_CUPS_extras.json` (junto al JSON principal)
gracias al trabajo de la sesión anterior. El sidecar es acumulativo: cada ciclo
añade las entradas nuevas sin borrar las antiguas.

Formato del sidecar:
```json
{
  "2026-03-01T00:00:00": {
    "generation_kWh": 0.0,
    "self_consumption_kWh": 0.0,
    "obtain_method": "Estimada"
  },
  "2026-03-15T12:00:00": {
    "generation_kWh": 1.452,
    "self_consumption_kWh": 0.980,
    "obtain_method": "Real"
  }
}
```

### Nuevas estadísticas a crear

| Statistic ID | Fuente | Tipo | Unidad |
|---|---|---|---|
| `edata:jk0f_generation` | `generation_kWh` del sidecar | sum, no mean | kWh |
| `edata:jk0f_self_consumption` | `self_consumption_kWh` del sidecar | sum, no mean | kWh |

### Cambios de código necesarios

**`coordinator.py`:**

1. Añadir `generation_stat_ids` y `self_consumption_stat_ids` en `__init__` (similar a `surplus_stat_ids`).
2. Añadir constantes en `const.py`:
   - `STAT_ID_GENERATION(id)`
   - `STAT_ID_SELF_CONSUMPTION(id)`
   - `STAT_TITLE_GENERATION(id, stat_id)`
   - `STAT_TITLE_SELF_CONSUMPTION(id, stat_id)`
3. Nuevo método `_update_solar_stats()` en coordinator:
   - Lee el sidecar completo
   - Para cada entrada con `generation_kWh > 0` o `self_consumption_kWh > 0`:
     - Construye `StatisticData(start=dt, sum=acumulado)`
   - Llama `async_add_external_statistics` con `StatisticMeanType.NONE`
4. Llamar `_update_solar_stats()` desde `update_statistics()` junto al resto.
5. El botón "Reimportar datos del periodo" también debe reconstruir estas estadísticas.

**`const.py`:** añadir las 4 constantes nuevas.

### Configuración en HA Energy (manual, una vez desplegado)

```
Panel Energía → Configurar:
  Consumo de red:     edata:jk0f_consumption      (ya existe)
  Retorno a red:      edata:jk0f_surplus           (ya existe)
  Producción solar:   edata:jk0f_generation        ← NUEVA
```

HA calculará automáticamente:
- `autoconsumo = generation - surplus`
- Balance neto en el diagrama de flujo

---

## Bloque 2 — Panel Lovelace de facturación completa

### Objetivo

Dashboard con toda la información energética + cálculo de factura real completa
mes a mes. El panel es autónomo: no depende del panel Energía de HA.

---

### 2.1 — Diagrama de sectores energético

Un gráfico de sectores (donut) por mes que muestra cómo se distribuye
la energía total disponible/consumida. Se proponen **dos vistas complementarias**:

#### Vista A — Origen del consumo de la casa

> ¿De dónde viene la energía que consumes?

| Sector | Valor | Fórmula |
|---|---|---|
| Importado de red | kWh | `value_kWh` |
| Autoconsumo solar | kWh | `self_consumption_kWh` |

```
Ejemplo marzo 2026:
  Importado red:   383.57 kWh  (60.8%)
  Autoconsumo:     247.31 kWh  (39.2%)
  ─────────────────────────────────────
  Total casa:      630.88 kWh (100%)
```

#### Vista B — Destino de la producción solar

> ¿Adónde va la energía que produces?

| Sector | Valor | Fórmula |
|---|---|---|
| Autoconsumo | kWh | `self_consumption_kWh` |
| Vertido a red | kWh | `surplus_kWh` |

```
Ejemplo marzo 2026:
  Autoconsumo:  247.31 kWh  (56.2%)
  Vertido:      192.81 kWh  (43.8%)
  ─────────────────────────────────
  Total solar:  440.13 kWh (100%)
```

Ambos diagramas muestran:
- Valor absoluto en kWh dentro o junto a cada sector
- Porcentaje sobre el total del sector
- Selector de mes para navegar el histórico

---

### 2.2 — Desglose de factura real

La factura eléctrica española PVPC/indexada tiene la siguiente estructura.
**Todos los términos ya están calculados** por `BillingProcessor` en `cost_monthly_sum`.

#### Estructura de factura real

```
TÉRMINO DE POTENCIA
  P1 (punta):   P1_kW × (peaje_P1_€/kW/año + mercado_€/kW/año) / 365 × días_mes
  P2 (valle):   P2_kW × (peaje_P2_€/kW/año)                    / 365 × días_mes
  ─────────────────────────────────────────────────────────────
  Subtotal potencia (sin impuestos):                             XX.XX €

TÉRMINO DE ENERGÍA
  Suma horaria: consumo_kWh × precio_PVPC_hora_€/kWh            XX.XX €

COMPENSACIÓN EXCEDENTES
  - Suma horaria: surplus_kWh × precio_PVPC_hora_€/kWh
    (compensación simplificada, nunca supera el término de energía)
                                                                -XX.XX €

OTROS SERVICIOS
  Alquiler de equipos de medida (contador):                      XX.XX €

SUBTOTAL ANTES DE IMPUESTOS:                                     XX.XX €

IMPUESTO SOBRE LA ELECTRICIDAD (5.11300560%)
  Subtotal × 1.0511300560                                        XX.XX €

IVA (5%)
  (Subtotal + IE) × 1.05                                        XX.XX €

══════════════════════════════════════════════════════════════
TOTAL FACTURA ESTIMADA:                                         XX.XX €
```

> **Nota:** La compensación de excedentes simplificada (modalidad más común en
> autoconsumo con excedentes) descuenta el valor del surplus del término de
> energía, pero nunca puede resultar en un importe negativo total.

#### Fuente de cada término en el código

| Término factura | Campo en `cost_monthly_sum` | Estado |
|---|---|---|
| Potencia P1+P2 | `power_term` | ✅ disponible |
| Energía importada | `energy_term` | ✅ disponible |
| Compensación surplus | `surplus_term` | ✅ disponible |
| Alquiler contador | `others_term` | ✅ disponible |
| Total (con impuestos) | `value_eur` | ✅ disponible |
| Potencia contratada P1 | atributo `contract_p1_kW` | ✅ disponible |
| Potencia contratada P2 | atributo `contract_p2_kW` | ✅ disponible |
| Precio hora PVPC | `cost_hourly_sum.value_eur_kWh` | ✅ disponible (horario) |

> `IE` e `IVA` están ya incorporados en los totales de `BillingProcessor`
> (ver fórmulas en `const.py`: `BILLING_ENERGY_FORMULA`, `BILLING_POWER_FORMULA`).
> El panel debe mostrarlos desglosados calculando la inversa desde los subtotales.

---

### 2.3 — Estructura completa del panel

```
┌─────────────────────────────────────────────────────────────────┐
│  PANEL ENERGÉTICO Y FACTURACIÓN           [◀ mes ▶]            │
│  Mes seleccionado: Marzo 2026                                   │
├─────────────────────────────────────────────────────────────────┤
│  RESUMEN ENERGÉTICO                                             │
│  ┌────────────┬─────────────┬──────────────┬─────────────┐     │
│  │ Importado  │  Producido  │ Autoconsumo  │   Vertido   │     │
│  │ 383.57 kWh │ 440.13 kWh  │ 247.31 kWh   │ 192.81 kWh  │     │
│  └────────────┴─────────────┴──────────────┴─────────────┘     │
├───────────────────────┬─────────────────────────────────────────┤
│  ORIGEN DEL CONSUMO   │  DESTINO DE LA PRODUCCIÓN SOLAR        │
│                       │                                         │
│   ╭───────────╮       │    ╭───────────╮                        │
│  ╱ Autocons.  ╲      │   ╱  Autocons.  ╲                       │
│ │  247 kWh    │      │  │   247 kWh     │                      │
│ │   39.2%     │      │  │    56.2%      │                      │
│  ╲  Red       ╱      │   ╲  Vertido    ╱                       │
│   ╰ 384 kWh ─╯       │    ╰ 193 kWh ─╯                        │
│      60.8%            │       43.8%                             │
├───────────────────────┴─────────────────────────────────────────┤
│  FACTURA ESTIMADA                                               │
│  Potencia (P1+P2):              XX.XX €                         │
│  Energía importada:             XX.XX €                         │
│  Compensación excedentes:      -XX.XX €                         │
│  Alquiler contador:             XX.XX €                         │
│  ──────────────────────────────────────                         │
│  Subtotal:                      XX.XX €                         │
│  Impuesto electricidad (5.11%): XX.XX €                         │
│  IVA (5%):                      XX.XX €                         │
│  ══════════════════════════════════════                         │
│  TOTAL:                         XX.XX €    [Ahorro solar: XX €] │
├─────────────────────────────────────────────────────────────────┤
│  HISTÓRICO 13 MESES — kWh (barras apiladas)                     │
│  ████ Importado red  ░░░░ Autoconsumo  ▒▒▒▒ Vertido             │
│  abr  may  jun  jul  ago  sep  oct  nov  dic  ene  feb  mar  abr│
├─────────────────────────────────────────────────────────────────┤
│  HISTÓRICO 13 MESES — Factura € (línea + barras)                │
│  ─── Total €   ████ Potencia  ░░░░ Energía  ▒▒▒▒ Excedente      │
└─────────────────────────────────────────────────────────────────┘
```

#### Nota sobre "Ahorro solar"

```
Ahorro solar (€/mes) = energía_autoconsumo × precio_medio_hora_€
                     + compensación_excedentes
```

No está en `cost_monthly_sum` directamente pero se puede calcular en el frontend
usando `self_consumption_kWh × (energy_term / value_kWh)` como aproximación,
o exponerlo como estadística propia si se quiere más precisión.

---

### Fuentes de datos para el panel

| Dato | Fuente | Estado |
|---|---|---|
| Importado red kWh/mes | `consumptions_monthly_sum.value_kWh` (websocket) | ✅ |
| Vertido red kWh/mes | `consumptions_monthly_sum.surplus_kWh` (websocket) | ✅ |
| Producción solar kWh/mes | sidecar `generation_kWh` agregado por mes | ❌ bloque 1 |
| Autoconsumo kWh/mes | sidecar `self_consumption_kWh` agregado por mes | ❌ bloque 1 |
| Potencia contratada P1/P2 | atributos `contract_p1_kW`, `contract_p2_kW` | ✅ |
| `power_term` €/mes | `cost_monthly_sum.power_term` (websocket) | ✅ |
| `energy_term` €/mes | `cost_monthly_sum.energy_term` (websocket) | ✅ |
| `surplus_term` €/mes | `cost_monthly_sum.surplus_term` (websocket) | ✅ |
| `others_term` €/mes | `cost_monthly_sum.others_term` (websocket) | ✅ |
| Total factura €/mes | `cost_monthly_sum.value_eur` (websocket) | ✅ |

### Cambios de código necesarios

**`websockets.py`:**
- Extender `WS_CONSUMPTIONS_MONTH` para incluir `generation_kWh` y
  `self_consumption_kWh` agregados por mes (desde el sidecar).
- Extender `WS_COSTS_MONTH` (o crear `WS_BILL_MONTH`) para incluir todos los
  sub-términos de factura: `power_term`, `energy_term`, `surplus_term`,
  `others_term`, `value_eur`.

**`www/edata-card.js`:**
- Nueva pestaña/vista `"facturación"` en la tarjeta existente.
- Dos gráficos donut SVG (origen consumo + destino producción) con:
  - Colores diferenciados por sector
  - Etiquetas con valor kWh y porcentaje
  - Animación al cambiar de mes
- Selector de mes con navegación ◀ ▶.
- Tabla de desglose de factura con los 7 líneas + total.
- Chip `"Ahorro solar: XX €"` calculado en frontend.
- Dos gráficos de barras apiladas históricas (kWh y €).

---

## Orden de implementación recomendado

1. **Bloque 1** — Estadísticas LTS `generation` + `self_consumption`
   - `const.py`: 4 constantes
   - `coordinator.py`: `_update_solar_stats()` + integración
   - Verificar panel Energía HA con diagrama de flujo correcto
2. **Websocket solar mensual**
   - Agregar sidecar por mes y exponerlo en `WS_CONSUMPTIONS_MONTH`
   - Añadir todos los sub-términos de coste a `WS_COSTS_MONTH`
3. **Panel Lovelace**
   - Donut charts (origen + destino)
   - Tabla de factura real
   - Barras históricas kWh y €
   - Chip de ahorro solar

---

## Notas técnicas

- El sidecar `edata_CUPS_extras.json` solo tiene datos desde el 23/04/2026.
  El histórico completo de 13 meses estará disponible ~25/04/2026.
- `IE` e `IVA` están ya incorporados en los totales de `BillingProcessor`.
  Para mostrarlos desglosados en el panel se calcula:
  - `subtotal_sin_impuestos = value_eur / 1.05 / 1.0511300560`
  - `IE = subtotal × 0.0511300560`
  - `IVA = (subtotal + IE) × 0.05`
- La compensación de excedentes simplificada nunca genera saldo positivo
  (la factura mínima es 0 €, no puede ser negativa).
- El "ahorro solar" es informativo: no aparece en la factura real pero
  es útil para evaluar el retorno de la inversión fotovoltaica.
- **`BILLING_SURPLUS_FORMULA` para PVPC**: usa `kwh_eur` (precio horario del pool)
  en lugar de `surplus_p1_kwh_eur`. En España la compensación simplificada se hace
  al precio horario del mercado spot — el mismo que `kwh_eur`. El valor por defecto
  de `surplus_p1_kwh_eur` es `None`, por lo que la fórmula original siempre daba 0.
  Para tarifas custom (no PVPC) el usuario debe configurar `surplus_p1_kwh_eur` manualmente.


> Estado: **PLANIFICACIÓN** — No implementar hasta autorización explícita.
> Última actualización: 2026-04-23

---

## Contexto y motivación

Datadis expone en su API cinco campos por hora de consumo:

| Campo API | Descripción |
|---|---|
| `consumptionKWh` | Energía importada de la red |
| `surplusEnergyKWh` | Energía vertida a la red |
| `generationEnergyKWh` | Producción solar total (autoconsumo + vertido) |
| `selfConsumptionEnergyKWh` | Solar consumido directamente en casa |
| `obtainMethod` | `"Real"` o `"Estimada"` |

La librería `edata` solo mapea `consumptionKWh` → `value_kWh` y `surplusEnergyKWh` → `surplus_kWh`. El resto se descarta.

### Balance energético verificado (marzo 2026)

```
Producción solar (generation):    440.13 kWh
  └─ Autoconsumo (self_cons):     247.31 kWh
  └─ Vertido a red (surplus):     192.81 kWh  ✅ coincide con surplus_kWh

Consumo total casa:
  Importado de red:               383.57 kWh
+ Autoconsumo:                    247.31 kWh
─────────────────────────────────────────────
Total (≈ Shelly):                 630.88 kWh  (Shelly: 618.77 → delta 2%)

Identidad comprobada:
  generation = selfConsumption + surplus → 440.13 == 440.13 ✅
```

---

## Bloque 1 — Estadísticas LTS para todos los campos de Datadis

### Objetivo

Exponer `generation_kWh` y `self_consumption_kWh` como estadísticas LTS en HA
para que el panel Energía pueda usarlos, y para que estén disponibles
para sensores, automatizaciones y dashboards.

### Persistencia actual (sidecar)

Los campos extra ya se almacenan en `edata_CUPS_extras.json` (junto al JSON principal)
gracias al trabajo de la sesión anterior. El sidecar es acumulativo: cada ciclo
añade las entradas nuevas sin borrar las antiguas.

Formato del sidecar:
```json
{
  "2026-03-01T00:00:00": {
    "generation_kWh": 0.0,
    "self_consumption_kWh": 0.0,
    "obtain_method": "Estimada"
  },
  "2026-03-15T12:00:00": {
    "generation_kWh": 1.452,
    "self_consumption_kWh": 0.980,
    "obtain_method": "Real"
  }
}
```

### Nuevas estadísticas a crear

| Statistic ID | Fuente | Tipo | Unidad |
|---|---|---|---|
| `edata:jk0f_generation` | `generation_kWh` del sidecar | sum, no mean | kWh |
| `edata:jk0f_self_consumption` | `self_consumption_kWh` del sidecar | sum, no mean | kWh |

### Cambios de código necesarios

**`coordinator.py`:**

1. Añadir `generation_stat_ids` y `self_consumption_stat_ids` en `__init__` (similar a `surplus_stat_ids`).
2. Añadir constantes en `const.py`:
   - `STAT_ID_GENERATION(id)`
   - `STAT_ID_SELF_CONSUMPTION(id)`
   - `STAT_TITLE_GENERATION(id, stat_id)`
   - `STAT_TITLE_SELF_CONSUMPTION(id, stat_id)`
3. Nuevo método `_update_solar_stats()` en coordinator:
   - Lee el sidecar completo
   - Para cada entrada con `generation_kWh > 0` o `self_consumption_kWh > 0`:
     - Construye `StatisticData(start=dt, sum=acumulado)`
   - Llama `async_add_external_statistics` con `StatisticMeanType.NONE`
4. Llamar `_update_solar_stats()` desde `update_statistics()` junto al resto.
5. El botón "Reimportar datos del periodo" también debe reconstruir estas estadísticas.

**`const.py`:** añadir las 4 constantes nuevas.

### Configuración en HA Energy (manual, una vez desplegado)

```
Panel Energía → Configurar:
  Consumo de red:     edata:jk0f_consumption      (ya existe)
  Retorno a red:      edata:jk0f_surplus           (ya existe)
  Producción solar:   edata:jk0f_generation        ← NUEVA
```

HA calculará automáticamente:
- `autoconsumo = generation - surplus`
- Balance neto en el diagrama de flujo

---

## Bloque 2 — Panel Lovelace de facturación completa

### Objetivo

Dashboard con toda la información energética + cálculo de factura completa
mes a mes, incluyendo término de potencia, energía, excedentes e impuestos.

### Fórmula de factura completa (PVPC / tarifa indexada)

```
Término de potencia (€/mes):
  P1_kW × (P1_kW_año_€ + mercado_kW_año_€) / 365 × días
+ P2_kW × P2_kW_año_€                       / 365 × días

Término de energía (€/mes):
  suma_horaria(consumo_kWh × precio_hora_€)

Excedente a compensar (€/mes):
  - suma_horaria(surplus_kWh × precio_hora_€)   [hasta 0]

Alquiler contador:
  € fijo / mes

Impuesto eléctrico:  × 1.0511300560
IVA:                 × 1.05
─────────────────────────────────────────────────
Total €/mes
```

> El cálculo de factura **ya existe** en la librería edata (`BillingProcessor`).
> Las estadísticas de coste (`cost_monthly_sum`) ya están disponibles.
> Lo que falta es **visualizarlo** de forma clara en un panel.

### Estructura propuesta del panel

```
┌─────────────────────────────────────────────────────────────┐
│  RESUMEN ENERGÉTICO MENSUAL          [selector mes]         │
├──────────────┬──────────────┬──────────────┬───────────────┤
│ Importado    │ Producido    │ Autoconsumo  │ Vertido       │
│ red (kWh)    │ solar (kWh)  │ (kWh)        │ red (kWh)     │
├──────────────┴──────────────┴──────────────┴───────────────┤
│              DIAGRAMA DE FLUJO ENERGÉTICO                    │
│   [Red] ──▶ [Casa]   [Solar] ──▶ [Casa]                     │
│                               └──▶ [Red]                    │
├─────────────────────────────────────────────────────────────┤
│  FACTURA ESTIMADA                                           │
│  Término energía:       XX.XX €                             │
│  Término potencia:      XX.XX €                             │
│  Excedente compensado: -XX.XX €                             │
│  Alquiler contador:     XX.XX €                             │
│  Impuesto eléctrico:    XX.XX €                             │
│  IVA:                   XX.XX €                             │
│  ─────────────────────────────                              │
│  TOTAL ESTIMADO:        XX.XX €                             │
├─────────────────────────────────────────────────────────────┤
│  HISTÓRICO MENSUAL (barras apiladas 13 meses)               │
│  [importado | autoconsumo | vertido | coste €]              │
└─────────────────────────────────────────────────────────────┘
```

### Fuentes de datos para el panel

| Dato | Fuente actual | Pendiente |
|---|---|---|
| Importado red (kWh/mes) | `consumptions_monthly_sum.value_kWh` (websocket) | ✅ disponible |
| Vertido red (kWh/mes) | `consumptions_monthly_sum.surplus_kWh` (websocket) | ✅ disponible |
| Producción solar (kWh/mes) | sidecar `generation_kWh` | ❌ bloque 1 |
| Autoconsumo (kWh/mes) | sidecar `self_consumption_kWh` | ❌ bloque 1 |
| Coste energía (€/mes) | `cost_monthly_sum.energy_term` (websocket) | ✅ disponible |
| Coste potencia (€/mes) | `cost_monthly_sum.power_term` (websocket) | ✅ disponible |
| Coste excedente (€/mes) | `cost_monthly_sum.surplus_term` (websocket) | ✅ disponible |
| Coste alquiler (€/mes) | `cost_monthly_sum.others_term` (websocket) | ✅ disponible |
| Total factura (€/mes) | `cost_monthly_sum.value_eur` (websocket) | ✅ disponible |

### Cambios de código necesarios

**`websockets.py`:**
- Exponer `generation_kWh` y `self_consumption_kWh` en `WS_CONSUMPTIONS_MONTH`
  (combinando `consumptions_monthly_sum` del JSON con el sidecar agregado por mes).

**`www/edata-card.js`:**
- Nueva vista "Facturación" en la tarjeta existente, o tarjeta nueva `edata-bill-card`.
- Selector de mes.
- Tabla de desglose de factura con los 6 términos.
- Gráfico de barras apiladas (importado / autoconsumo / vertido) por mes.
- Diagrama de flujo simplificado (opcional, puede reutilizar el existente).

---

## Orden de implementación recomendado

1. **Bloque 1 completo** — estadísticas `generation` y `self_consumption`
   - `const.py`: 4 constantes
   - `coordinator.py`: `_update_solar_stats()` + integración en `update_statistics()`
   - Verificar que HA Energy muestra el diagrama de flujo correcto
2. **Websocket generation/self_consumption mensual**
   - Extender `WS_CONSUMPTIONS_MONTH` con datos del sidecar
3. **Panel Lovelace**
   - Desglose de factura mes a mes
   - Barras apiladas históricas
   - Diagrama de flujo

---

## Notas técnicas

- El sidecar `edata_CUPS_extras.json` solo tiene datos desde que se desplegó
  la nueva versión (23/04/2026). El histórico de `generation` y `self_consumption`
  se irá llenando ciclo a ciclo (cada 24h). Los primeros 13 meses completos
  estarán disponibles aproximadamente en 25-26/04/2026 (cuando expire la caché
  y se repita la descarga completa).
- `obtain_method` no necesita estadística LTS — puede exponerse como atributo
  del sensor de consumo o ignorarse en el panel.
- El cálculo de factura existente (`BillingProcessor`) ya incluye todos los
  términos. No hay que reimplementarlo, solo visualizarlo.
