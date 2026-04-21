# Instrucciones para agentes en este repositorio

Lo primero en cualquier tarea de análisis, documentación o implementación es consultar de forma selectiva la documentación del proyecto.

## Regla obligatoria de consulta selectiva

1. Empieza siempre por `docs/DOCUMENTATION_MAP.md`.
2. A partir de ese mapa, localiza sólo los documentos relevantes para la tarea actual.
3. No cargues toda la documentación si el cambio afecta a una sola superficie.
4. Si una tarea cambia el diseño, el comportamiento o la estructura documental, actualiza la documentación afectada al finalizar.

## Regla obligatoria de actualización progresiva

La documentación de este repositorio debe mantenerse de forma progresiva tras cada tarea de:

- análisis
- documentación
- implementación

Esto implica:

1. Actualizar el documento temático afectado en `docs/`.
2. Actualizar `docs/DOCUMENTATION_MAP.md` si cambió la estructura o aparecieron nuevos documentos.
3. Actualizar este fichero si cambian las reglas de trabajo del agente.

## Orden recomendado de trabajo

1. Consultar `docs/DOCUMENTATION_MAP.md`.
2. Leer sólo la documentación mínima necesaria.
3. Revisar el código concreto a modificar.
4. Implementar o documentar el cambio.
5. Validar el cambio.
6. Refrescar la documentación correspondiente antes de cerrar la tarea.

## Guía de consulta por superficie

- Arquitectura interna: `docs/ARCHITECTURE.md`
- Flujo de configuración y entidades: `docs/CONFIGURATION_AND_ENTITIES.md`
- Persistencia y estadísticas: `docs/DATA_MODEL_AND_STATISTICS.md`
- Tarjeta y websockets: `docs/FRONTEND_AND_WEBSOCKETS.md`
- CI, empaquetado y release: `docs/DEVELOPMENT_AND_RELEASE.md`
- Trabajo específico del fork sobre vertido: `docs/FORK_SURPLUS_STATUS.md`
- Operación del fork y sincronización con upstream: `docs/FORK_OPERATION.md`

## Criterios de edición

- Priorizar cambios pequeños y localizados.
- No asumir que el soporte de `surplus` está completo: comprobar siempre la capa exacta afectada.
- Si aparece una discrepancia entre documentación y código, corregirla en la misma tarea.
- Mantener el README como guía de usuario y `docs/` como documentación técnica y de mantenimiento.