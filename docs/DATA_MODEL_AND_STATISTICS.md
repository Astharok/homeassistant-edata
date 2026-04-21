# Modelo de datos y estadísticas

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

## Implicaciones para el trabajo sobre vertido

El soporte de vertido ya entra en el flujo de datos principal:

- existe atributo `surplus_kWh`
- existe histórico websocket de `surplus`
- existe estadística `surplus`
- existe coste `surplus_cost`

Lo que no está completamente homogéneo es la trazabilidad por periodos tarifarios y su exposición uniforme en opciones, formularios y posiblemente parte de la UI.