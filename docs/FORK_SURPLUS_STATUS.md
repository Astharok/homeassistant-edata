# Estado del fork y soporte de vertido

> Última actualización: 2026-04-24 (v2 — revisión UX + corrección surplus)

## Objetivo del fork

Mantener una variante propia de `homeassistant-edata` con soporte completo de
datos solares (generación, autoconsumo, vertido), facturación real española y
panel Lovelace de dashboard energético.

---

## Estado actual (2026-04-24 — auditoría de robustez + revisión UX)

### ✅ Completado en esta rama

| Área | Implementación |
|---|---|
| Sidecar `generation_kWh` + `self_consumption_kWh` | Persistencia acumulativa, aplicación en memoria cada ciclo |
| **Sidecar con escritura atómica** | `tempfile + os.replace` garantiza que un kill de HA mid-write no corrompe el fichero |
| **Detección de sidecar corrupto** | Si `json.load` falla, fichero se renombra a `.corrupt-<ts>.json` y se notifica al usuario vía `persistent_notification` |
| **Alerta de fallo persistente en Datadis** | Tras 3 ciclos consecutivos con fallo, se crea `persistent_notification` (se limpia automáticamente al recuperar) |
| **Alerta de fallo de backup** | Si `shutil.copy2` falla en la rotación diaria, se avisa al usuario con la ruta del directorio |
| LTS stats `edata:<scups>_generation` / `_self_consumption` | `StatisticMeanType.NONE`, `has_sum=True`, `unit_class="energy"` |
| Enriquecimiento websocket mensual | `_enrich_monthly_with_sidecar()` añade solar + terms de coste + `savings_term` por ciclo de facturación |
| Panel `edata-solar-card` | KPIs, tabla P1/P2/P3, donuts, tabla de factura, ahorro autoconsumo, históricos |
| **Panel con re-fetch automático** | La tarjeta observa el estado del sensor edata y re-fetcha al cambiar, evitando quedarse en "Cargando" |
| **Compensación excedentes unificada** | UI expone un único campo `surplus_p1_kwh_eur` (la compensación simplificada en España es igual para P1/P2/P3). P2/P3 se reflejan automáticamente al construir `pricing_rules` |
| **Fórmula surplus por defecto corregida** | Antes: `electricity_tax * iva_tax * surplus_kwh * surplus_p1_kwh_eur` (añadía IVA + impuesto eléctrico incorrectos). Ahora: `surplus_kwh * surplus_kwh_eur` (sin impuestos — compensación se descuenta en bruto antes del IVA) |
| **Variables y fórmulas sugeridas en UI** | El paso `formulas` muestra `description` con la lista completa de variables disponibles y `data_description` por campo con la fórmula sugerida según PVPC/flat |
| **Desglose simulación siempre visible** | El selector de mes muestra `MM/YYYY · Total X € · E... · P... · −Vert... · ☀...` en la etiqueta, garantizando que el usuario vea los totales incluso si el frontend de HA no renderiza la `description` markdown |
| **Log de validación de surplus** | `simulate_billing` imprime por mes `input_kwh` / `input_surplus_kwh` y un sanity check `surplus_kwh * price = esperado € (bruto / con tax)` para diagnosticar discrepancias |
| **Modo debug = nivel DEBUG** | `CONF_DEBUG=true` ahora pone el logger en `logging.DEBUG` (antes `INFO`); añadido volcado per-month en el ciclo de actualización con kWh, surplus, generación, autoconsumo y todos los términos de coste |
| Fix `TemplateSelector` → `TextSelector` | Evitaba UndefinedError en fórmulas al guardar |
| Fix `PREVENT_EXTRA` generalizado | `_clean_consumptions()` context manager en todos los call sites |
| Lecturas sidecar en executor | Sin bloqueo del event loop |
| Fix `KeyError` en `options_update_listener` | Al desactivar billing, `update_billing_since` ausente → crash; corregido con `.get()` |
| Fix `UnboundLocalError` en `_update_cost_stats` | Si `get_pvpc_tariff` devuelve valor inesperado → variables sin asignar; corregido con `else: continue` |
| Fix `from_now` ignorado en `ws_get_cost` | El parámetro se calculaba pero no se pasaba a `get_costs_history`; corregido |
| Fix `_stat_id` sin asignar en `utils.py` | Tres funciones: corregido con `else: return []` |
| **Higiene de logs** | ~20 `_LOGGER.warning()` rutinarios del ciclo de actualización y de `simulate_billing` degradados a `INFO`; `WARNING` queda para condiciones anómalas reales |

### ⚠️ Huecos abiertos restantes

#### Hueco A — LTS por periodo para excedente

`const.py` define `STAT_ID_P1/P2/P3_SURP_KWH` pero el coordinador sólo publica
`edata:<scups>_surplus` agregado. Para explotar vertido por tarifa en el panel
Energía de HA habría que añadir estas stats. Depende de disponibilidad en
`e-data` de `surplus_p1_kWh / p2_kWh / p3_kWh` a nivel horario/diario.

#### Hueco B — Websocket `surplus` sin selector de tarifa

`edata/ws/surplus` devuelve excedente total sin discriminar por periodo.

### ⚠️ Huecos abiertos restantes

#### Hueco A — LTS por periodo para excedente

`const.py` define `STAT_ID_P1/P2/P3_SURP_KWH` pero el coordinador sólo publica
`edata:<scups>_surplus` agregado. Para explotar vertido por tarifa en el panel
Energía de HA habría que añadir estas stats. Depende de disponibilidad en
`e-data` de `surplus_p1_kWh / p2_kWh / p3_kWh` a nivel horario/diario.

#### Hueco B — Websocket `surplus` sin selector de tarifa

`edata/ws/surplus` devuelve excedente total sin discriminar por periodo.

#### Hueco C — Validación end-to-end automatizada

No hay tests automáticos. La validación es manual en HA con datos reales.

---

## Invariantes de robustez garantizadas

- **Nunca se pierden datos por fallo de dump**: `_clean_consumptions` usa `try/finally` para restaurar extras aunque `dump_storage` lance excepción.
- **Nunca se corrompe el sidecar**: escritura vía `tmp + os.replace` (atómica en POSIX y Windows Python 3.3+).
- **Sidecar corrupto se aísla, no se pierde**: el fichero dañado se conserva como `.corrupt-<ts>.json` para forensic.
- **Backups rotativos diarios con retención de 30 días**: se salta rotación si el fichero principal está vacío o ilegible (no se sobrescribe un backup con basura).
- **Reimport con snapshot local**: `_async_force_reimport_period` aprovecha backups disponibles antes de rellamar a Datadis.
- **Estadísticas LTS reconstruibles**: `check_statistics_integrity` + `rebuild_statistics` + botones `soft_reset`, `import_all_data`, `force_surplus_reimport`.
- **Alertas al usuario** para: recarga forzada, fallos repetidos de Datadis, sidecar corrupto, fallo en backup diario.

---

## Lectura recomendada antes de tocar vertido

1. `docs/CONFIGURATION_AND_ENTITIES.md`
2. `docs/DATA_MODEL_AND_STATISTICS.md`
3. `docs/FRONTEND_AND_WEBSOCKETS.md`

---

## Roadmap pendiente

### Fase siguiente — Stats LTS por periodo de excedente (Hueco A)

- Detectar si `e-data` expone `surplus_pX_kWh` en `consumptions` o `consumptions_daily_sum`
- Registrar `edata:<scups>_pX_surplus` si hay datos disponibles
- Alinear `_update_consumption_stats` con la lógica existente por tarifa

### Fase siguiente — Tests automáticos

- Documentar procedimiento de prueba reproducible con datos de ejemplo
- Verificar alta, descarga, sensores, estadísticas y tarjeta

---

## Criterio de mantenimiento

Cada tarea sobre excedentes o datos solares debe actualizar este documento con:
- estado alcanzado
- huecos cerrados
- nuevos riesgos detectados

## Objetivo del fork

El objetivo de este fork es independizarse del repositorio original y mantener una variante propia de `homeassistant-edata` con soporte de datos de vertido o excedentes bien integrado y probado.

## Qué soporte de vertido existe ya en el código

Tras revisar el repositorio actual, hay evidencia clara de soporte ya implementado en varias capas:

- constantes de configuración y facturación para `surplus`
- sensores energéticos de excedente diario, último día registrado, mes actual y último mes
- websocket `edata/ws/surplus`
- soporte de gráfico `surplus` en `edata-card.js`
- estadísticas `edata:<scups>_surplus`
- coste de excedente `edata:<scups>_surplus_cost`
- traducciones de UI para opciones y etiquetas relacionadas con excedentes

## Estado real: soporte presente pero no completamente consolidado

Hay señales de que el trabajo sobre vertido está avanzado, pero no totalmente cerrado:

### Hueco 1. Configuración de precios por periodo no homogénea

`const.py` define precios de compensación para `P1`, `P2` y `P3`, pero `schemas.py` sólo expone el campo `surplus_p1_kwh_eur` en el formulario de opciones. La UI, por tanto, no refleja todavía toda la granularidad sugerida por las constantes y traducciones.

Como medida de coherencia operativa, el fork oculta además la compensación de excedentes cuando el usuario configura PVPC, porque ese escenario sigue sin estar soportado de forma consistente.

### Hueco 2. Reglas usadas al montar `pricing_rules`

En `__init__.py` y `config_flow.py`, el empaquetado de reglas de facturación incluye `surplus_p1_kwh_eur`, pero no `surplus_p2_kwh_eur` ni `surplus_p3_kwh_eur`. Eso indica que el backend operativo sigue orientado a una compensación única o, al menos, a P1.

### Hueco 3. Exposición websocket de excedente por tarifa

La API websocket actual para `surplus` devuelve histórico agregado, sin selector de tarifa. Si en el futuro quieres explotar excedente por periodos, hay que ampliar ese contrato o asumir explícitamente que el dato público seguirá siendo agregado total.

### Hueco 4. Necesidad de validación end-to-end

El repositorio no incluye tests automáticos que demuestren que el cálculo de vertido funciona de extremo a extremo. A día de hoy, la validación fiable depende de una prueba manual en Home Assistant con datos reales o representativos.

## Lectura recomendada antes de tocar vertido

Consulta de forma selectiva:

1. `docs/CONFIGURATION_AND_ENTITIES.md`
2. `docs/DATA_MODEL_AND_STATISTICS.md`
3. `docs/FRONTEND_AND_WEBSOCKETS.md`

## Propuesta de roadmap técnico

### Fase 1. Consolidar el fork

- actualizar nombres, URLs y metadatos del repositorio
- mantener este paquete documental como base del fork

Estado actual: las referencias principales del componente ya apuntan a `Astharok/homeassistant-edata`, aunque la publicación efectiva dependerá de crear y subir la rama remota `main` en el fork.

### Fase 2. Cerrar el soporte de vertido en backend

- decidir si la compensación será única o por tarifa
- alinear `const.py`, `schemas.py`, `config_flow.py` y `__init__.py`
- revisar cómo la librería `e-data` entrega datos y reglas de `surplus`

### Fase 3. Cerrar el soporte de vertido en frontend

- validar `edata/ws/surplus`
- validar tarjetas `surplus` y resúmenes
- revisar nombres de entidades y traducciones de costes de excedente

### Fase 4. Pruebas manuales reproducibles

- documentar un procedimiento de prueba en Home Assistant
- verificar alta de integración, descarga de datos, sensores, estadísticas y tarjeta

## Criterio de mantenimiento para este documento

Cada vez que se haga una tarea sobre excedentes o vertido, este documento debe actualizarse con:

- el estado real alcanzado
- huecos cerrados
- nuevos riesgos detectados
- siguiente paso recomendado