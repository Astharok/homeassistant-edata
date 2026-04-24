# Mapa de documentación

> Última actualización: 2026-04-24

Este documento es el índice operativo de la documentación del proyecto. Su función
es permitir una consulta selectiva y rápida: antes de leer documentación, localiza
aquí el área relevante y abre sólo los ficheros necesarios.

## Cómo usar este mapa

1. Identifica el tipo de tarea: análisis, depuración, documentación, implementación o release.
2. Busca en la tabla el área funcional afectada.
3. Consulta únicamente los documentos indicados para esa tarea.
4. Tras completar la tarea, actualiza el documento afectado y este mapa si has creado,
   movido o dividido documentación.

## Mapa de ficheros

| Ruta | Contenido | Cuándo consultarlo |
|---|---|---|
| `docs/PROJECT_OVERVIEW.md` | Requisitos funcionales completos, alcance, dependencias, estado del fork. | Primer punto de entrada. Valida qué hace el proyecto y cuál es el estado de cada área. |
| `docs/ARCHITECTURE.md` | Arquitectura interna, ciclo de vida de HA y responsabilidades por módulo. | Cuando vayas a tocar la inicialización, el coordinador o la separación entre capas. |
| `docs/CONFIGURATION_AND_ENTITIES.md` | Flujo de configuración, opciones, entidades, traducciones. | Cuando trabajes en `config_flow.py`, `schemas.py`, `sensor.py`, `button.py` o traducciones. |
| `docs/DATA_MODEL_AND_STATISTICS.md` | Persistencia, sidecar, stats LTS, context manager `_clean_consumptions`, enriquecimiento WS. | Cuando cambies cálculo de datos, almacenamiento, estadísticas o sidecar solar. |
| `docs/FRONTEND_AND_WEBSOCKETS.md` | API websocket v1/v2, `edata-card`, `edata-solar-card`, contrato de datos. | Cuando modifiques `websockets.py` o `www/edata-card.js`. |
| `docs/DEVELOPMENT_AND_RELEASE.md` | Estructura de repo, CI, validaciones, empaquetado y publicación. | Cuando prepares cambios, revises workflows o publiques releases. |
| `docs/FORK_SURPLUS_STATUS.md` | Estado del fork solar: huecos cerrados, abiertos y siguiente plan. | Cuando trabajes en energía solar, vertido, facturación o dashboard. |
| `docs/FORK_OPERATION.md` | Procedimientos operativos: migración HACS, trabajo en `main`, sincronización upstream. | Cuando necesites instalar tu fork en HA o actualizarlo con cambios del repo original. |
| `docs/FINALIZE_MAIN_BRANCH.md` | Paso final para eliminar `dev` cuando `main` ya existe en remoto. | Cuando GitHub bloquee el borrado de `dev` por ser rama por defecto. |
| `docs/ROADMAP_SOLAR_DASHBOARD.md` | Plan técnico (implementado) del dashboard solar y facturación completa. | Referencia histórica del diseño; para cambios futuros en el panel solar. |
| `.github/copilot-instructions.md` | Reglas operativas para agentes y mantenimiento progresivo de la documentación. | Siempre al iniciar una tarea automatizada en el repositorio. |

## Guía de consulta selectiva por tarea

| Tarea | Documentos mínimos |
|---|---|
| Entender el proyecto por primera vez | `docs/PROJECT_OVERVIEW.md` |
| Tocar inicialización o coordinador | `docs/ARCHITECTURE.md`, `docs/DATA_MODEL_AND_STATISTICS.md` |
| Cambiar el flujo de configuración | `docs/CONFIGURATION_AND_ENTITIES.md`, `docs/FORK_SURPLUS_STATUS.md` |
| Modificar sensores, botones o traducciones | `docs/CONFIGURATION_AND_ENTITIES.md` |
| Trabajar en solar / vertido / facturación | `docs/FORK_SURPLUS_STATUS.md`, `docs/DATA_MODEL_AND_STATISTICS.md`, `docs/FRONTEND_AND_WEBSOCKETS.md` |
| Ajustar websockets o tarjeta Lovelace | `docs/FRONTEND_AND_WEBSOCKETS.md` |
| Preparar release o revisar CI | `docs/DEVELOPMENT_AND_RELEASE.md` |
| Migrar HA al fork o traer cambios del upstream | `docs/FORK_OPERATION.md`, `docs/DEVELOPMENT_AND_RELEASE.md` |

## Regla de mantenimiento

La documentación debe evolucionar junto con el código. Después de cada tarea:

1. Actualiza el documento temático afectado.
2. Si cambió la estructura documental, actualiza este mapa.
3. Si el cambio afecta a la forma de trabajar del agente, actualiza `.github/copilot-instructions.md`.

Este documento es el índice operativo de la documentación del proyecto. Su función es permitir una consulta selectiva y rápida: antes de leer documentación, localiza aquí el área relevante y abre sólo los ficheros necesarios.

## Cómo usar este mapa

1. Identifica el tipo de tarea: análisis, depuración, documentación, implementación o release.
2. Busca en la tabla el área funcional afectada.
3. Consulta únicamente los documentos indicados para esa tarea.
4. Tras completar la tarea, actualiza el documento afectado y este mapa si has creado, movido o dividido documentación.

## Mapa de ficheros

| Ruta | Contenido | Cuándo consultarlo |
| --- | --- | --- |
| `docs/PROJECT_OVERVIEW.md` | Visión general del proyecto, dependencias, alcance funcional y limitaciones. | Cuando necesitas contexto rápido del componente o validar qué hace el proyecto. |
| `docs/ARCHITECTURE.md` | Arquitectura interna, ciclo de vida de Home Assistant y responsabilidades por módulo. | Cuando vayas a tocar la inicialización, el coordinador o la separación entre capas. |
| `docs/CONFIGURATION_AND_ENTITIES.md` | Flujo de configuración, opciones, entidades, traducciones y superficies funcionales expuestas a HA. | Cuando trabajes en `config_flow.py`, `schemas.py`, `sensor.py`, `button.py` o traducciones. |
| `docs/DATA_MODEL_AND_STATISTICS.md` | Persistencia, estadísticas, caché, migraciones y recorrido de datos desde Datadis hasta HA. | Cuando cambies cálculo de datos, almacenamiento o estadísticas. |
| `docs/FRONTEND_AND_WEBSOCKETS.md` | API websocket, tarjeta Lovelace `edata-card` y contrato frontend-backend. | Cuando modifiques `websockets.py` o `www/edata-card.js`. |
| `docs/DEVELOPMENT_AND_RELEASE.md` | Estructura de repo, CI, validaciones, empaquetado y publicación. | Cuando prepares cambios, revises workflows o publiques releases. |
| `docs/FORK_SURPLUS_STATUS.md` | Estado actual del fork orientado a vertido/excedentes, huecos detectados y siguiente plan técnico. | Cuando trabajes en energía vertida, facturación de excedentes o tu estrategia de fork propio. |
| `docs/FORK_OPERATION.md` | Procedimientos operativos del fork: migración en HACS, trabajo en `main` y sincronización con upstream. | Cuando necesites instalar tu fork en Home Assistant o actualizarlo con cambios del repositorio original. |
| `docs/FINALIZE_MAIN_BRANCH.md` | Paso final para eliminar `dev` cuando `main` ya existe en remoto. | Cuando GitHub bloquee el borrado de `dev` por ser rama por defecto. |
| `docs/ROADMAP_SOLAR_DASHBOARD.md` | Plan detallado: estadísticas LTS de generación/autoconsumo + panel de facturación completa. | Cuando se implemente el bloque solar o el panel Lovelace de facturación. |
| `.github/copilot-instructions.md` | Reglas operativas para agentes y mantenimiento progresivo de la documentación. | Siempre al iniciar una tarea automatizada en el repositorio. |

## Guía de consulta selectiva por tarea

| Tarea | Documentos mínimos |
| --- | --- |
| Entender el proyecto por primera vez | `docs/PROJECT_OVERVIEW.md` |
| Tocar inicialización o coordinador | `docs/ARCHITECTURE.md`, `docs/DATA_MODEL_AND_STATISTICS.md` |
| Cambiar el flujo de configuración | `docs/CONFIGURATION_AND_ENTITIES.md`, `docs/FORK_SURPLUS_STATUS.md` |
| Modificar sensores, botones o traducciones | `docs/CONFIGURATION_AND_ENTITIES.md` |
| Trabajar en vertido/excedentes | `docs/FORK_SURPLUS_STATUS.md`, `docs/DATA_MODEL_AND_STATISTICS.md`, `docs/FRONTEND_AND_WEBSOCKETS.md` |
| Ajustar websockets o tarjeta | `docs/FRONTEND_AND_WEBSOCKETS.md` |
| Preparar release o revisar CI | `docs/DEVELOPMENT_AND_RELEASE.md` |
| Migrar Home Assistant al fork o traer cambios del upstream | `docs/FORK_OPERATION.md`, `docs/DEVELOPMENT_AND_RELEASE.md` |

## Regla de mantenimiento

La documentación debe evolucionar junto con el código. Después de cada tarea de análisis, documentación o implementación:

1. Actualiza el documento temático afectado.
2. Si cambió la estructura documental, actualiza este mapa.
3. Si el cambio afecta a la forma de trabajar del agente, actualiza `.github/copilot-instructions.md`.