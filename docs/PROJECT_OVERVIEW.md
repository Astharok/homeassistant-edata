# Visión general del proyecto

> Última actualización: 2026-04-24  
> Rama: `main` — fork de `uvejota/homeassistant-edata` mantenido por `Astharok`

---

## Qué es este repositorio

`homeassistant-edata` es una integración custom de Home Assistant para Datadis,
a través de la librería Python `e-data`. Su objetivo es descargar histórico
energético de un suministro eléctrico, persistirlo localmente, proyectarlo en
estadísticas de Home Assistant y exponerlo como:

- sensores y botones del dispositivo `edata`
- estadísticas LTS utilizables por el panel de Energía de HA
- datos agregados accesibles por websocket
- una tarjeta Lovelace propia (`edata-card` y `edata-solar-card`)

---

## Requisitos funcionales

### RF-01 — Descarga de datos desde Datadis

- La integración se autentica en Datadis con usuario y contraseña.
- Soporta suministros con NIF autorizado opcional (titular diferente al usuario).
- Descarga consumo horario (`value_kWh`, `surplus_kWh`) hasta los últimos 13 meses.
- Descarga campos ampliados cuando están disponibles: `generation_kWh`,
  `self_consumption_kWh`, `obtain_method`.
- Los campos ampliados no disponibles en la librería `e-data` se persisten en un
  fichero sidecar propio (`edata_CUPS_extras.json`) y se restauran en memoria
  en cada ciclo de actualización.

### RF-02 — Persistencia local

- Los datos se persisten en `<HA_STORAGE>/edata/edata_<cups>.json` mediante la
  librería `e-data`.
- Los campos extra (generación, autoconsumo, método) se persisten en
  `<HA_STORAGE>/edata/edata_<cups>_extras.json` gestionado directamente por
  el coordinador.
- Se mantiene un backup diario rotativo en
  `<HA_STORAGE>/edata/backups/edata_<cups>_<YYYY-MM-DD>.json`
  con retención de 30 días.

### RF-03 — Estadísticas LTS en Home Assistant

Las siguientes estadísticas externas se registran en el `recorder` de HA:

| Grupo | Statistic IDs | Unidad |
|---|---|---|
| Consumo | `edata:<scups>_consumption`, `_p1/p2/p3_consumption` | kWh |
| Excedente | `edata:<scups>_surplus` | kWh |
| Solar | `edata:<scups>_generation`, `edata:<scups>_self_consumption` | kWh |
| Maxímetro | `edata:<scups>_maximeter`, `_p1/p2_maximeter` | kW |
| Coste | `edata:<scups>_cost`, `_p1/p2/p3_cost`, `_energy_cost`, `_p1/p2/p3_energy_cost`, `_power_cost`, `_surplus_cost` | € |

Los stats de coste sólo se activan si la facturación está habilitada.

### RF-04 — Sensores expuestos

- Sensor de estado: fecha del último dato registrado.
- Sensores de energía: consumo diario, mes actual, último mes (total y por tarifa P1/P2/P3).
- Sensores de excedente: vertido diario, mes actual, último mes.
- Sensores de potencia maxímetro: último valor registrado, mes actual.
- Sensores de coste: coste mes actual, último mes (total y por componente).

### RF-05 — Facturación

- Configurable: PVPC (precios de mercado spot) o tarifa plana con precios manuales.
- Fórmulas de cálculo personalizables para energía, potencia, otros y surplus.
- Fórmulas PVPC por defecto implementadas para la estructura real de factura española:
  - término de potencia P1+P2 (peaje + mercado)
  - término de energía (suma horaria × precio spot)
  - compensación de excedentes simplificada (suma horaria × precio spot, tope= energía)
  - alquiler de contador
  - IE (5.1130056%)
  - IVA (5%)
- Simulación de la factura del mes anterior visible en el flujo de configuración antes
  de confirmar los cambios.
- Ciclo de facturación configurable (día de inicio del periodo mensual).

### RF-06 — Panel Lovelace solar (`edata-solar-card`)

- Navegación mes a mes con selector ◀▶.
- KPI chips: importado, producido, autoconsumo, vertido (kWh).
- Donut "Origen del consumo": importado de red vs autoconsumo solar (valores + %).
- Donut "Destino de la producción": autoconsumo vs vertido (valores + %).
- Tabla de factura real: potencia, energía, compensación, contador, total.
- Chip de ahorro solar estimado (€).
- Barras históricas kWh (13 meses, apiladas: importado + autoconsumo + vertido).
- Barras históricas € (13 meses, apiladas por componente de factura).

### RF-07 — Panel Lovelace general (`edata-card`)

- Gráficas de consumo, excedente, maxímetro y costes.
- Plantillas: `consumptions`, `surplus`, `maximeter`, `costs`, `summary-*`.
- Agregaciones: hora, día, semana, mes, año.

### RF-08 — Botones de mantenimiento

- **Reset suave**: fuerza una actualización normal sin limpiar histórico.
- **Importar datos del periodo**: fuerza reimportación de un rango de fechas,
  usando snapshot local si existe o rellamando a Datadis.

### RF-09 — Robustez y compatibilidad

- Los extras inyectados en memoria se limpian temporalmente antes de llamar a
  funciones de la librería que usan `EdataSchema` (PREVENT_EXTRA), usando el
  context manager `_clean_consumptions`. Los valores se restauran al salir.
- El sidecar se lee siempre en un executor para no bloquear el event loop.
- `unit_class="energy"` declarado en stats kWh para compatibilidad con HA 2026.11+.
- Legacy strip de `{{ }}` en valores de fórmula guardados con versiones antiguas.

---

## Alcance NO funcional (fuera de este fork)

- Soporte de múltiples suministros en un único hogar (cada CUPS crea su propia
  entrada de configuración independiente).
- Tiempo real: la latencia depende de Datadis, típicamente de varios días.
- Tarificación por periodos P2/P3 de excedentes (pendiente, ver RF-05 y
  `FORK_SURPLUS_STATUS.md`).

---

## Dependencias principales

| Dependencia | Versión | Rol |
|---|---|---|
| `e-data` | 1.2.22 | Descarga Datadis, schema de datos, BillingProcessor |
| `python-dateutil` | ≥2.8.2 | Cálculo de rangos y offsets mensuales |
| HA `lovelace` | — | Registro automático de recurso JS |
| HA `recorder` | — | Almacén de estadísticas LTS |

---

## Estructura principal del repositorio

| Ruta | Responsabilidad |
|---|---|
| `custom_components/edata/__init__.py` | Bootstrap: recursos frontend, entidades, websockets. |
| `custom_components/edata/config_flow.py` | Alta de suministro y flujo de opciones de facturación. |
| `custom_components/edata/schemas.py` | Selectores y defaults de formularios. |
| `custom_components/edata/coordinator.py` | Núcleo: descarga, sidecar, estadísticas, facturación. |
| `custom_components/edata/sensor.py` | Sensores expuestos a HA. |
| `custom_components/edata/button.py` | Botones de mantenimiento. |
| `custom_components/edata/websockets.py` | API websocket para frontend. |
| `custom_components/edata/www/edata-card.js` | Tarjeta `edata-card` + `edata-solar-card`. |
| `custom_components/edata/translations/` | Traducciones en, es, ca, gl. |
| `docs/` | Documentación técnica y operativa del fork. |

---

## Estado del fork respecto al estado del arte

| Área | Estado |
|---|---|
| Consumo energético (P1/P2/P3) | ✅ Completo |
| Excedente / vertido | ✅ Completo (compensación PVPC simplificada) |
| Generación solar + autoconsumo | ✅ Implementado (sidecar + LTS stats) |
| Panel solar Lovelace | ✅ Implementado (`edata-solar-card`) |
| Facturación completa real | ✅ Implementado (fórmulas PVPC + custom) |
| Compensación por tarifa P2/P3 | ⚠️ Pendiente (ver `FORK_SURPLUS_STATUS.md`) |
| Tests automáticos | ❌ No implementados |

## Qué es este repositorio

`homeassistant-edata` es una integración custom de Home Assistant para Datadis a través de la librería Python `e-data`. Su objetivo es descargar histórico energético de un suministro eléctrico, persistirlo de forma local, proyectarlo en estadísticas de Home Assistant y exponerlo como:

- sensores y botones del dispositivo `edata`
- estadísticas utilizables por el panel de Energía
- datos agregados accesibles por websocket
- una tarjeta Lovelace propia (`edata-card`)

## Alcance funcional actual

En el estado actual del repositorio, la integración contempla estas áreas:

- consumo energético total y por periodos P1/P2/P3
- excedente o vertido energético (`surplus`) a nivel de sensores, estadísticas y websocket
- potencia máxima registrada (`maximeter`)
- simulación y cálculo de facturación
- visualización mediante tarjeta nativa y tarjetas de terceros

## Dependencias principales

Dependencias declaradas en `custom_components/edata/manifest.json`:

- `e-data==1.2.22`
- `python-dateutil>=2.8.2`

Dependencias funcionales de Home Assistant:

- `lovelace`
- `recorder`

La integración está diseñada como `cloud_polling`, porque depende de datos remotos de Datadis y éstos no son en tiempo real.

## Estructura principal del repositorio

| Ruta | Responsabilidad |
| --- | --- |
| `custom_components/edata/__init__.py` | Punto de entrada de Home Assistant, alta de recursos frontend y registro de websockets. |
| `custom_components/edata/config_flow.py` | Alta inicial del suministro y flujo de opciones. |
| `custom_components/edata/coordinator.py` | Coordinador central: descarga, persistencia, sincronización y estadísticas. |
| `custom_components/edata/sensor.py` | Sensores expuestos por la integración. |
| `custom_components/edata/button.py` | Botones de mantenimiento y resync. |
| `custom_components/edata/websockets.py` | API websocket consumida por frontend o tarjetas externas. |
| `custom_components/edata/www/edata-card.js` | Tarjeta Lovelace propia. |
| `custom_components/edata/translations/` | Traducciones de UI y nombres de entidades. |
| `.github/workflows/` | Validación CI, HACS, hassfest y publicación de release. |
| `docs/` | Documentación técnica y operativa del fork. |

## Limitaciones conocidas del proyecto

- Los datos no son en tiempo real. La latencia depende de Datadis y puede ser de varios días.
- La integración depende de la disponibilidad y consistencia de la API de Datadis.
- La tarificación y la compensación de excedentes no están cerradas de forma homogénea en todas las capas del proyecto. Hay soporte visible, pero también trazas de trabajo en progreso.
- `services.yaml` existe, pero no hay evidencia de registro efectivo de servicios en el código actual.

## Estado del fork respecto a vertido

Tu objetivo de crear un fork propio añadiendo vertido está alineado con el código actual: el repositorio ya contiene soporte parcial o avanzado para `surplus`, pero no parece completamente consolidado en todas las rutas. Esa situación se detalla en `docs/FORK_SURPLUS_STATUS.md`.