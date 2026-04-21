# Visión general del proyecto

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