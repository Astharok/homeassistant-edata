# Operación del fork

## Rama de trabajo

Este fork se mantiene trabajando directamente sobre `main`.

Las ramas históricas `dev` y `energiaVertida` dejan de ser la referencia operativa. A efectos de mantenimiento:

- el desarrollo normal se hace sobre `main`
- los workflows del fork escuchan `main`
- cualquier sincronización con el repositorio original debe integrarse sobre `main`

## Configuración git recomendada

Mantén dos remotos configurados:

- `origin`: tu fork `https://github.com/Astharok/homeassistant-edata.git`
- `upstream`: repositorio original `https://github.com/uvejota/homeassistant-edata.git`

Comprobación rápida:

```powershell
git remote -v
```

Si falta `upstream`, añádelo:

```powershell
git remote add upstream https://github.com/uvejota/homeassistant-edata.git
git fetch upstream --tags
```

## Cómo migrar Home Assistant desde el repo original al fork

Contexto: actualmente Home Assistant usa el repositorio original `https://github.com/uvejota/homeassistant-edata` a través de HACS y quieres pasar a `https://github.com/Astharok/homeassistant-edata`.

### Objetivo de la migración

Cambiar el origen del componente en HACS sin perder la configuración funcional de la integración `edata` en Home Assistant.

### Procedimiento recomendado

1. Haz una copia de seguridad de Home Assistant.
2. En HACS, abre la integración `e-data` instalada actualmente y anota la versión que estás usando.
3. Elimina de HACS el repositorio personalizado antiguo si lo tienes añadido manualmente: `https://github.com/uvejota/homeassistant-edata`.
4. Añade como repositorio personalizado en HACS: `https://github.com/Astharok/homeassistant-edata` con categoría `Integration`.
5. Instala o reinstala la integración desde tu fork en HACS.
6. Reinicia Home Assistant.
7. Verifica que la integración `edata` sigue apareciendo en `Ajustes > Dispositivos y servicios`.
8. Comprueba que las entidades `sensor.edata_*`, la tarjeta y los datos históricos siguen disponibles.

### Incidencia conocida: "Downloading ... with version <hash> failed"

Si HACS muestra un error como `Downloading Astharok/homeassistant-edata with version <hash> failed`, revisa:

1. Rama por defecto del repositorio en GitHub:
   - mientras sea `dev`, HACS intentará descargar `dev`
   - cuando cambies la rama por defecto a `main`, HACS tomará `main`
2. Configuración de `hacs.json`:
   - para evitar dependencia de artefactos de release, este fork usa `"zip_release": false`

Con `zip_release: false`, HACS descarga el contenido del repositorio directamente desde rama/commit y evita fallos por ausencia de zip publicado.

### Qué no hacer salvo que sea imprescindible

- no elimines la entrada de configuración de la integración desde `Dispositivos y servicios` si sólo estás cambiando el origen del código
- no borres la carpeta de almacenamiento de Home Assistant asociada a `edata`
- no fuerces una reconfiguración completa si el dominio y los `unique_id` se mantienen iguales, como ocurre en este fork

### Validación posterior a la migración

Comprueba al menos lo siguiente:

- carga correcta de la integración
- sensores principales de consumo y excedente
- disponibilidad de la tarjeta `edata-card`
- histórico en panel de Energía y estadísticas si ya lo usabas
- opciones de facturación sin errores visibles

## Validar con logs y comprobar estadísticas

Sí, se puede validar con logs de forma objetiva. Este fork ya emite trazas resumidas si activas depuración.

### Activar logs útiles

1. En Home Assistant: `Ajustes > Dispositivos y servicios > e-data > Configurar`.
2. Activa la opción `debug` de la integración.
3. Reinicia Home Assistant.

Opcionalmente, en `configuration.yaml` puedes forzar niveles de log:

```yaml
logger:
   default: warning
   logs:
      custom_components.edata: info
      edata: info
```

### Qué líneas buscar en el log

En `home-assistant.log`, filtra por `custom_components.edata` y busca estas trazas:

- `refresh summary consumptions=... costs=... maximeter=... range=...`
- `statistics batch edata:...=N, edata:...=N`
- `import_all_data pressed ...`

Interpretación rápida:

- `refresh summary` confirma cuántos registros se descargaron desde Datadis y su rango temporal.
- `surplus_nonzero` y `surplus_total` en `refresh summary` indican si Datadis está devolviendo excedente en ese lote.
- `statistics batch` confirma cuántos puntos nuevos se han escrito por cada `statistic_id`.
- Si aparece `statistics batch has no new values`, no hay datos nuevos para insertar (normal si ya estaba al día).
- `import_all_data pressed ...` te avisa cuántas veces se ha lanzado la importación manual y el tiempo transcurrido desde la anterior.

### Verificación cruzada en Home Assistant

1. `Herramientas para desarrolladores > Estadísticas`.
2. Busca IDs como:
    - `edata:<scups>_consumption`
    - `edata:<scups>_surplus`
    - `edata:<scups>_surplus_cost` (si facturación activa)
3. Comprueba que las fechas y acumulados coinciden con los lotes del log.
4. En el sensor `sensor.edata_<scups>` revisa atributos:
   - `import_all_data_calls`
   - `import_all_data_last_run`

### Qué compartir para revisión técnica

Si quieres que revise contigo que todo está correcto, comparte:

- 1 bloque `refresh summary`
- 1 bloque `statistics batch`
- 1 línea `import_all_data pressed`
- el `scups` afectado
- si facturación está activada o no

## Nota sobre límites de llamadas y botón "Importar todos los datos"

La integración usa la librería `e-data`, que internamente ya cachea y limita parte del tráfico. Aun así, lanzar importaciones completas seguidas no suele aportar datos nuevos si Datadis no ha actualizado histórico.

Recomendación práctica:

- usa el botón de importación completa sólo cuando detectes huecos o tras cambios relevantes de facturación/configuración
- evita pulsarlo repetidamente en pocos minutos
- valida primero en log si `surplus_nonzero` sigue en 0: si es 0 de forma persistente, el problema puede ser ausencia de datos de vertido en origen (Datadis) y no la estadística de Home Assistant

## Cómo traer cambios del repositorio original de forma sencilla

La estrategia recomendada es mantener siempre `main` de tu fork por delante del upstream y traer cambios del original mediante merge controlado.

### Procedimiento de actualización

```powershell
git checkout main
git fetch origin
git fetch upstream --tags
git merge upstream/dev
```

Si en el futuro el repositorio original cambia su rama principal de desarrollo, sustituye `upstream/dev` por la rama correcta.

### Después del merge

1. Resuelve conflictos, especialmente en:
   - `custom_components/edata/config_flow.py`
   - `custom_components/edata/schemas.py`
   - `custom_components/edata/coordinator.py`
   - `custom_components/edata/sensor.py`
2. Revisa que no se hayan perdido los cambios del fork sobre excedentes.
3. Actualiza `docs/FORK_SURPLUS_STATUS.md` si cambia el estado del soporte de vertido.
4. Valida el resultado en Home Assistant.

### Regla práctica para merges futuros

Si el upstream toca una capa que tú no has modificado, acepta el cambio del upstream.

Si el upstream toca una capa donde tu fork añade vertido o compensación de excedentes, revisa manualmente el merge y prioriza mantener:

- sensores de excedente
- estadísticas `surplus`
- coste `surplus_cost`
- traducciones asociadas
- referencias a tu fork en metadatos

## Checklist corto de sincronización

1. `git checkout main`
2. `git fetch upstream --tags`
3. `git merge upstream/dev`
4. revisar conflictos
5. validar Home Assistant
6. actualizar documentación del fork
7. `git push origin main`