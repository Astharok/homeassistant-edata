# Frontend y websockets

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