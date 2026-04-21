# Desarrollo y release

## Estructura de validación actual

El repositorio incluye cuatro workflows en `.github/workflows/`:

### `python-app.yml`

Ejecuta en pushes y pull requests contra `main`:

- instalación de dependencias base
- `flake8`

Observaciones:

- el workflow asume Python 3.8
- instala `requirements.txt` sólo si existe, pero actualmente no hay `requirements.txt` en la raíz del repo
- no ejecuta tests automáticos reales del componente

### `hacs.yml`

Valida compatibilidad con HACS.

### `hassfest.yml`

Ejecuta validación de Home Assistant mediante `hassfest`.

### `release.yml`

Gestiona dos vías:

- release publicada: empaqueta `custom_components/edata` en `homeassistant-edata.zip` y la sube a GitHub Releases
- rama `main`: genera o actualiza una prerelease continua con tag `main`

## Paquete distribuible

El zip de distribución contiene exclusivamente el contenido de `custom_components/edata/`.

Esto implica que:

- la carpeta `docs/` no afecta al artefacto HACS
- la documentación del fork puede crecer sin riesgo para el paquete final

## HACS y metadatos

Metadatos relevantes:

- `hacs.json` habilita render del README y empaquetado zip release
- `manifest.json` define versión, dependencias y documentación
- las URLs operativas del fork deben apuntar al repositorio propio y no al original

## Recomendaciones operativas para este fork

1. Mantener la documentación técnica en `docs/` y no mezclarla con la guía de usuario del README salvo enlaces mínimos.
2. Validar cada cambio que toque `config_flow.py`, `coordinator.py` o `websockets.py` con al menos `hassfest` y una prueba manual en Home Assistant.
3. Antes de publicar tu fork, revisar `manifest.json`, `hacs.json`, URLs de documentación e `issue_tracker` para que apunten a tu repositorio y no al original.

En el estado actual del repo local, `manifest.json`, README y la tarjeta frontend ya están alineados con `Astharok/homeassistant-edata`.

La automatización del fork también queda alineada con `main`, que pasa a ser la rama única de trabajo prevista.

## Lagunas actuales del entorno de desarrollo

- No hay suite de tests del componente dentro del repositorio.
- No hay documentación técnica previa del diseño interno; esta carpeta `docs/` cubre ese hueco.
- No hay automatización visible para pruebas integradas con Home Assistant Core o container de desarrollo.

## Checklist previo a publicar tu fork

1. Renombrar metadatos del repositorio y referencias URL.
2. Revisar estado real del soporte de `surplus` de extremo a extremo.
3. Probar instalación HACS y configuración completa en una instancia de Home Assistant.
4. Validar traducciones y nombres de entidades nuevas o modificadas.
5. Publicar release zip desde tu propio repositorio.