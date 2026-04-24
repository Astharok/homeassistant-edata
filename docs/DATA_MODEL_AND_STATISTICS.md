# Modelo de datos y estadísticas

> Última actualización: 2026-04-24

## Flujo de datos

El recorrido principal de datos es:

1. Datadis expone datos remotos por CUPS.
2. La librería `e-data` los descarga y persiste en disco (JSON local).
3. `EdataCoordinator` enriquece los datos en memoria con el sidecar de extras.
4. Se vuelca a disco (sin los extras, para respetar el schema de la librería).
5. Se sincronizan estadísticas externas al `recorder` de HA.
6. Sensores, websockets y frontend consumen atributos y estadísticas.

## Persistencia local

### Fichero principal (librería e-data)

- Ruta: `<STORAGE>/edata/edata_<cups>.json`
- Gestionado por `e-data` via `dump_storage` / `load_storage`.
- Contiene: `consumptions`, `contracts`, `supplies`, `maximeter`, `pvpc`, `cost_hourly_sum`, etc.
- Schema: `EdataSchema` (voluptuous, `PREVENT_EXTRA`).  
  **Importante**: las claves extra (`generation_kWh`, `self_consumption_kWh`, `obtain_method`)
  deben estar ausentes al llamar a `dump_storage`, `BillingProcessor` o `process_data`.
  El context manager `_clean_consumptions()` en `coordinator.py` gestiona esto.

### Sidecar de extras (coordinador)

- Ruta: `<STORAGE>/edata/edata_<cups>_extras.json`
- Gestionado directamente por el coordinador.
- Contiene los campos que la librería descarta al persistir: `generation_kWh`,
  `self_consumption_kWh`, `obtain_method`.
- Formato: `{"ISO_datetime_str": {"generation_kWh": float, "self_consumption_kWh": float, "obtain_method": str}}`
- Acumulativo: cada ciclo añade entradas nuevas sin borrar las antiguas.
- Se lee siempre en un executor (sin bloquear el event loop).

### Backups rotativos (coordinador)

- Ruta: `<STORAGE>/edata/backups/edata_<cups>_<YYYY-MM-DD>.json`
- Copia diaria del fichero principal tras cada descarga exitosa.
- Retención: 30 días.
- Usado por `_async_force_reimport_period` cuando hay snapshot disponible,
  evitando llamadas adicionales a Datadis.

## Ventana de caché

| Modo | Meses | Cuándo se usa |
|---|---|---|
| Normal (`CACHE_MONTHS_SHORT`) | 13 | Ciclo periódico de actualización |
| Forzado (`CACHE_MONTHS_LONG`) | 23 | Botón de importación completa |

La ventana comienza el día 1 del mes N-cache_months y termina el fin del día anterior.

## Estadísticas externas registradas

Todas usan `async_add_external_statistics`. Las de tipo kWh llevan `unit_class="energy"`
para compatibilidad con HA 2026.11+.

### Consumo energético

| Statistic ID | Tipo | Unidad |
|---|---|---|
| `edata:<scups>_consumption` | sum, no mean | kWh |
| `edata:<scups>_p1_consumption` | sum, no mean | kWh |
| `edata:<scups>_p2_consumption` | sum, no mean | kWh |
| `edata:<scups>_p3_consumption` | sum, no mean | kWh |

### Excedente / vertido

| Statistic ID | Tipo | Unidad |
|---|---|---|
| `edata:<scups>_surplus` | sum, no mean | kWh |

### Solar (nuevo — sidecar)

| Statistic ID | Fuente | Tipo | Unidad |
|---|---|---|---|
| `edata:<scups>_generation` | `generation_kWh` del sidecar | sum, no mean | kWh |
| `edata:<scups>_self_consumption` | `self_consumption_kWh` del sidecar | sum, no mean | kWh |

Configurar en el panel Energía de HA: `edata:<scups>_generation` como fuente solar.

### Maxímetro

| Statistic ID | Tipo | Unidad |
|---|---|---|
| `edata:<scups>_maximeter` | mean, no sum | kW |
| `edata:<scups>_p1_maximeter` | mean, no sum | kW |
| `edata:<scups>_p2_maximeter` | mean, no sum | kW |

### Costes (sólo si facturación habilitada)

| Statistic ID | Descripción | Unidad |
|---|---|---|
| `edata:<scups>_cost` | Total por hora | € |
| `edata:<scups>_p1/p2/p3_cost` | Total por periodo | € |
| `edata:<scups>_energy_cost` | Término de energía | € |
| `edata:<scups>_p1/p2/p3_energy_cost` | Energía por periodo | € |
| `edata:<scups>_power_cost` | Término de potencia | € |
| `edata:<scups>_surplus_cost` | Compensación excedentes | € |

## Enriquecimiento del websocket mensual

`_enrich_monthly_with_sidecar()` añade a cada registro mensual:

| Campo | Origen |
|---|---|
| `generation_kWh` | Sidecar, agregado por ciclo de facturación |
| `self_consumption_kWh` | Sidecar, agregado por ciclo de facturación |
| `energy_term` | `cost_monthly_sum` de la librería |
| `power_term` | `cost_monthly_sum` de la librería |
| `surplus_term` | `cost_monthly_sum` de la librería |
| `others_term` | `cost_monthly_sum` de la librería |
| `value_eur` | `cost_monthly_sum` de la librería |

La agregación sidecar respeta `cycle_start_day` (offset de ciclo de facturación).

## Fuente de lectura para histórico

`utils.py` usa dos estrategias:

- memoria o datos locales recientes (`fetch_changes_from_mem`)
- estadísticas del recorder (`fetch_changes_from_stats`)

La selección ocurre en `fetch_changes()`, que intenta primero lectura desde memoria
y cae a estadísticas si no es suficiente.

## Agregaciones soportadas por websocket

`hour`, `day`, `week`, `month`, `year`. Para `year` se reagrupan resultados mensuales
con `group_by_year()`.

## Integridad y reparación de estadísticas

`coordinator.py` implementa:

- `_update_last_stats_summary`: obtiene el último punto persistido por `statistic_id`.
- `check_statistics_integrity`: compara suma de estadísticas con suma de datos fuente.
- `rebuild_statistics`: borra y reconstruye desde un `from_dt` dado.
- `_async_force_reimport_period`: reimportación de un rango completo, usando snapshot
  local si existe o rellamando a Datadis.

Todos estos métodos usan `_clean_consumptions()` antes de llamar a la librería.

## Context manager `_clean_consumptions`

```python
@contextlib.contextmanager
def _clean_consumptions(consumptions):
    # Pop _EXTRAS_KEYS on enter, restore on exit (even on exception)
```

Aplicado a todos los call sites de `process_data`, `process_cost` y `dump_storage`
para evitar errores `voluptuous.Invalid` por `PREVENT_EXTRA`.

## Flujo de datos

El recorrido principal de datos es:

1. Datadis expone datos remotos.
2. La librería `e-data` los descarga y persiste en disco.
3. `EdataCoordinator` procesa, resume y sincroniza esos datos.
4. Home Assistant recibe estadísticas externas en `recorder`.
5. Sensores, websockets y frontend consumen atributos o estadísticas agregadas.

## Persistencia local

La librería `e-data` recibe `storage_dir_path=self.hass.config.path(STORAGE_DIR)` y escribe sus datos dentro del almacenamiento de Home Assistant.

La integración también incluye una migración de storage en `migrate.py`:

- origen antiguo: `<STORAGE_DIR>/edata.storage_<ID>`
- destino actual: `<STORAGE_DIR>/edata/edata_<cups>.json`

La migración se ejecuta al construir el coordinador.

## Ventana de caché

`EdataCoordinator` define:

- `CACHE_MONTHS_SHORT = 13`
- `CACHE_MONTHS_LONG = 23`

Por defecto usa la ventana corta para recuperar desde el primer día del mes menos 13 meses hasta el final del día anterior.

Cuando la actualización es automática (coordinador periódico), se respetan las limitaciones normales de caché/rate-limit de `e-data`.

Cuando la actualización se lanza manualmente con botones de forzado, el coordinador limpia la caché de consultas de Datadis y reinicia marcas de última actualización para forzar descarga real.

Para reducir llamadas repetidas al API, los botones de forzado guardan una instantánea local del periodo recargado en storage. Si se vuelve a lanzar la misma recarga (mismo inicio de periodo y misma ventana de caché), se reutiliza esa instantánea sin hacer nuevas llamadas a Datadis.

## Estadísticas externas registradas

### Consumo

- `edata:<scups>_consumption`
- `edata:<scups>_p1_consumption`
- `edata:<scups>_p2_consumption`
- `edata:<scups>_p3_consumption`

### Excedente / vertido

- `edata:<scups>_surplus`
- constantes definidas también para `p1_surplus`, `p2_surplus`, `p3_surplus`

Aunque existen IDs por periodo para excedente, en el coordinador actual el conjunto principal de estadísticas de excedente usa explícitamente sólo `edata:<scups>_surplus` como grupo funcional activo.

### Maxímetro

- `edata:<scups>_maximeter`
- `edata:<scups>_p1_maximeter`
- `edata:<scups>_p2_maximeter`

### Costes

- `edata:<scups>_cost`
- `edata:<scups>_p1_cost`
- `edata:<scups>_p2_cost`
- `edata:<scups>_p3_cost`
- `edata:<scups>_energy_cost`
- `edata:<scups>_p1_energy_cost`
- `edata:<scups>_p2_energy_cost`
- `edata:<scups>_p3_energy_cost`
- `edata:<scups>_power_cost`
- `edata:<scups>_surplus_cost`

Estas estadísticas de costes sólo se activan cuando hay reglas de facturación.

## Fuente de lectura para histórico

`utils.py` usa dos estrategias:

- memoria o datos locales recientes (`fetch_changes_from_mem`)
- estadísticas del recorder (`fetch_changes_from_stats`)

La selección ocurre en `fetch_changes()`, que intenta primero una lectura rápida desde memoria y cae a estadísticas si no es suficiente.

## Agregaciones soportadas

Para histórico por websocket se soportan estas agregaciones:

- `hour`
- `day`
- `week`
- `month`
- `year`

Para `year`, la integración reagrupa resultados mensuales en `group_by_year()`.

## Integridad y reparación de estadísticas

`coordinator.py` contiene lógica para:

- descubrir último valor persistido por `statistic_id`
- comprobar integridad entre datos fuente y estadísticas registradas
- reconstruir estadísticas cuando detecta divergencias

Esto es especialmente relevante cuando:

- cambia la configuración de facturación
- se importa histórico completo
- aparecen huecos o duplicados por respuestas irregulares de Datadis

Además, el botón `force_surplus_reimport` aplica una reconstrucción por periodo: borra y recalcula estadísticas desde el inicio del periodo recargado, preservando valores previos a ese punto.

## Implicaciones para el trabajo sobre vertido

El soporte de vertido ya entra en el flujo de datos principal:

- existe atributo `surplus_kWh`
- existe histórico websocket de `surplus`
- existe estadística `surplus`
- existe coste `surplus_cost`

Lo que no está completamente homogéneo es la trazabilidad por periodos tarifarios y su exposición uniforme en opciones, formularios y posiblemente parte de la UI.