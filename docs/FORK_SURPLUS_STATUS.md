# Estado del fork y soporte de vertido

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