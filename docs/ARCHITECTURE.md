# Arquitectura

## Resumen de arquitectura

La integración sigue un patrón clásico de Home Assistant basado en:

1. `config_flow.py` para recopilar credenciales y elegir el suministro.
2. `__init__.py` para inicializar recursos globales y dar de alta la entrada.
3. `EdataCoordinator` como capa central de sincronización y estado compartido.
4. entidades (`sensor.py`, `button.py`) como proyección de datos del coordinador.
5. `websockets.py` y `www/edata-card.js` como interfaz de consulta y visualización.

## Ciclo de vida

### 1. Arranque global de integración

`async_setup` en `__init__.py` registra el recurso estático `edata-card.js` dentro de Home Assistant y lo añade a Lovelace como recurso JS versionado.

### 2. Alta de una entrada configurada

`async_setup_entry` en `__init__.py`:

- recupera credenciales y opciones
- construye reglas de facturación si están activadas
- crea el `EdataCoordinator`
- retrasa la primera sincronización hasta que HA haya terminado de arrancar
- carga plataformas `button` y `sensor`
- registra los comandos websocket

### 3. Sincronización de datos

`EdataCoordinator._async_update_data()` invoca a la librería `e-data` para descargar datos históricos, actualiza estadísticas de HA y finalmente carga atributos y datos agregados en `hass.data`.

### 4. Proyección a entidades y frontend

- Las entidades leen estado y atributos desde `hass.data[DOMAIN][scups]`.
- Los websockets consultan `hass.data` o estadísticas del recorder.
- La tarjeta frontend consume websockets para construir gráficas y resúmenes.

## Responsabilidades por módulo

| Módulo | Rol principal | Observaciones |
| --- | --- | --- |
| `__init__.py` | Bootstrap de integración | Ensambla configuración, coordinador, plataformas y websockets. |
| `config_flow.py` | UX de configuración | Gestiona login Datadis, selección de CUPS y opciones de facturación. |
| `schemas.py` | Definición de formularios | Centraliza selectores y defaults del flujo de opciones. |
| `coordinator.py` | Núcleo de negocio | Descarga datos, migra storage, recalcula estadísticas, gestiona integridad y actualizaciones. |
| `entity.py` | Abstracciones de entidad | Define `DeviceInfo`, `unique_id` y acceso coordinado a datos. |
| `sensor.py` | Sensores expuestos | Declara sensores de info, energía, potencia y coste. |
| `button.py` | Acciones manuales | Expone reset suave e importación total. |
| `utils.py` | Utilidades transversales | Validación CUPS, recursos Lovelace, acceso a estadísticas y agregaciones. |
| `websockets.py` | API de lectura | Expone histórico agregado de consumo, excedente, costes, maxímetro y resumen. |
| `migrate.py` | Compatibilidad histórica | Migra almacenamiento pre-2024 al nuevo esquema de ficheros. |

## Estado compartido

La integración usa `hass.data[const.DOMAIN][scups.lower()]` como almacén compartido por entrada de configuración. Ahí conviven:

- referencia a la instancia `edata` de la librería externa
- coordinador
- atributos calculados
- estado del suministro
- caché websocket diaria/mensual/maxímetro

Esto reduce duplicación entre entidades y frontend, pero también convierte al coordinador en el punto crítico para cualquier cambio funcional.

## Decisiones arquitectónicas relevantes

### Uso combinado de storage local y estadísticas de HA

El proyecto no depende sólo del `recorder`. La librería `e-data` persiste datos descargados en disco y luego la integración vuelca estadísticas externas a Home Assistant. Esa combinación es la clave para:

- reconstruir histórico
- acelerar consultas recientes
- alimentar el panel de Energía
- soportar websockets con distintos niveles de agregación

### Websocket API versionada de forma informal

`websockets.py` mantiene una API antigua (`edata/consumptions/daily`, `edata/consumptions/monthly`, `edata/maximeter`) y otra más general (`edata/ws/...`). El frontend nuevo trabaja sobre la segunda, pero la primera todavía existe por compatibilidad.

### Recurso frontend autocargado

La tarjeta `edata-card.js` no requiere que el usuario registre manualmente el recurso si la integración se ha inicializado correctamente. `utils.init_resource()` lo da de alta o lo actualiza en Lovelace.

## Riesgos arquitectónicos a tener presentes

- `coordinator.py` concentra demasiada responsabilidad y conviene tratarlo como superficie delicada.
- Hay lógica de excedentes en varias capas y no toda parece simétrica entre P1, P2 y P3.
- La presencia de `services.yaml` sin registro explícito sugiere funcionalidad incompleta o arrastrada de versiones anteriores.