# Estado del fork y soporte de vertido

> Última actualización: 2026-04-24

## Objetivo del fork

Mantener una variante propia de `homeassistant-edata` con soporte completo de
datos solares (generación, autoconsumo, vertido), facturación real española y
panel Lovelace de dashboard energético.

---

## Estado actual (2026-04-24)

### ✅ Completado en esta rama

| Área | Implementación |
|---|---|
| Sidecar `generation_kWh` + `self_consumption_kWh` | Persistencia acumulativa, aplicación en memoria cada ciclo |
| LTS stats `edata:<scups>_generation` / `_self_consumption` | `StatisticMeanType.NONE`, `has_sum=True`, `unit_class="energy"` |
| Enriquecimiento websocket mensual | `_enrich_monthly_with_sidecar()` añade solar + terms de coste |
| Panel `edata-solar-card` | Donuts, tabla factura, histórico, chip ahorro |
| Fórmula surplus PVPC corregida | Usaba `surplus_p1_kwh_eur` (None → 0); ahora usa `kwh_eur` (precio spot) |
| Fix `TemplateSelector` → `TextSelector` | Evitaba UndefinedError en fórmulas al guardar |
| Fix `PREVENT_EXTRA` generalizado | `_clean_consumptions()` context manager en todos los call sites |
| Lecturas sidecar en executor | Sin bloqueo del event loop |

### ⚠️ Huecos abiertos

#### Hueco 1 — Compensación excedentes por tarifa P2/P3

`const.py` define `PRICE_SURP_P2_KWH`, `PRICE_SURP_P3_KWH` pero:
- `schemas.py` sólo expone `surplus_p1_kwh_eur` en el formulario
- `config_flow.py` y `__init__.py` sólo empaquetan `surplus_p1_kwh_eur`
- La fórmula PVPC por defecto compensa con precio spot (correcto para simplificada)
- La fórmula custom sólo tiene un campo `surplus_formula` global

Si el usuario quiere compensación diferenciada P1/P2/P3, no tiene UI para ello.

#### Hueco 2 — Validación end-to-end automatizada

No hay tests automáticos. La validación es manual en HA con datos reales.

#### Hueco 3 — Websocket `surplus` sin selector de tarifa

`edata/ws/surplus` devuelve excedente total sin discriminar por periodo.
Para uso avanzado con compensación diferenciada habría que ampliar el contrato.

---

## Lectura recomendada antes de tocar vertido

1. `docs/CONFIGURATION_AND_ENTITIES.md`
2. `docs/DATA_MODEL_AND_STATISTICS.md`
3. `docs/FRONTEND_AND_WEBSOCKETS.md`

---

## Roadmap pendiente

### Fase siguiente — Cerrar compensación por tarifa (opcional)

- Añadir `surplus_p2_kwh_eur` y `surplus_p3_kwh_eur` en `schemas.py` y `config_flow.py`
- Alinear la fórmula surplus con una expresión condicional por periodo, o
  mantener un único campo de precio y documentar la limitación explícitamente

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