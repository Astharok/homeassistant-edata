# Finalizar transición a main (paso único pendiente)

Estado actual ya completado:

- `main` existe en remoto y contiene todos los cambios del fork.
- la rama remota `energiaVertida` ya fue eliminada.
- queda pendiente eliminar `dev`, pero GitHub lo bloquea porque es la rama por defecto actual.

## Paso pendiente en GitHub (1 minuto)

1. Abrir: `https://github.com/Astharok/homeassistant-edata/settings/branches`
2. En **Default branch**, cambiar de `dev` a `main`.
3. Guardar cambios.

## Borrar rama dev después del cambio

Ejecuta en local dentro del repo:

```powershell
git push origin --delete dev
```

Con eso quedará el fork completamente alineado a trabajo sobre `main`.

## Verificación rápida

```powershell
git ls-remote --heads origin
```

Resultado esperado: solo `main` (o, como mucho, alguna rama temporal que crees en el futuro).
