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