# Configuración y entidades

## Flujo inicial de configuración

El alta del componente ocurre en dos pasos dentro de `config_flow.py`:

1. `async_step_user`
2. `async_step_choosecups`

### `async_step_user`

Solicita:

- `username`
- `password`
- `authorized_nif` opcional

Después valida credenciales contra Datadis mediante `test_login()` y lista los suministros asociados.

### `async_step_choosecups`

Permite seleccionar el `CUPS` a configurar y calcula un `scups` no colisionante usando sufijos progresivos del identificador.

## Flujo de opciones

`OptionsFlowHandler` implementa una configuración en varias fases:

1. `init`
2. `costs`
3. `formulas`
4. `confirm`

### Paso `init`

Opciones principales:

- `debug`
- `billing`
- `pvpc`
- `surplus`

La opción `surplus` ya aparece en formularios y traducciones, lo que confirma que el soporte de excedentes forma parte del diseño del fork actual.

### Paso `costs`

Se definen precios base y, según el caso:

- precios PVPC
- precios fijos P1/P2/P3
- compensación de excedentes

`schemas.py` expone un único campo `surplus_p1_kwh_eur` cuando `surplus` está
activado (la compensación simplificada española aplica el mismo €/kWh en todos
los periodos). En `__init__.py` y `config_flow.py` ese único valor se refleja a
`surplus_p2_kwh_eur` y `surplus_p3_kwh_eur` al construir `pricing_rules`, de modo
que `BillingProcessor` recibe los 3 campos que espera y expone la variable
derivada `surplus_kwh_eur` a las fórmulas.

La UI de opciones trata la compensación de excedentes como no soportada en modo
PVPC: el bloque de compensación queda oculto cuando `pvpc` está activado para no
presentar una configuración que el backend no soporta de forma coherente.

### Paso `formulas`

Cada término (`energy`, `power`, `others`, `surplus`) es una expresión Jinja2
evaluada por BillingProcessor hora a hora. La pantalla muestra:

- Descripción con la lista de variables disponibles (`kwh`, `surplus_kwh`,
  `kwh_eur`, `surplus_kwh_eur`, `p1_kw`, `p2_kw`, precios configurados, impuestos).
- `data_description` por campo con la fórmula sugerida — distinta según PVPC o
  tarifa plana.

Las fórmulas por defecto nuevas (const.py):

- Energía: `electricity_tax * iva_tax * kwh_eur * kwh`
- Potencia: `electricity_tax * iva_tax * (p1_kw * p1_kw_year_eur + p2_kw * p2_kw_year_eur) / 365 / 24`
- Otros: `iva_tax * meter_month_eur / 30 / 24`
- Excedente (flat): `surplus_kwh * surplus_kwh_eur`
- Excedente (PVPC): `surplus_kwh * kwh_eur`

La compensación simplificada NO lleva IVA ni impuesto eléctrico encima: se
descuenta al gross del importe energético antes de repercutir IVA sobre el neto.
Por eso el término `surplus_term` sale "limpio" y el total es una suma directa
de términos positivos y negativos.

### Paso `confirm`

Presenta la simulación como un formulario con el desglose completo como campos
de solo lectura (`ConstantSelector`). Se muestran, para el mes seleccionado,
estos términos:

- Mes · horas facturadas
- Energía importada (con impuestos)
- Potencia contratada (con impuestos)
- Otros (contador, bono social, con impuestos)
- Compensación excedentes (se resta)
- Ahorro autoconsumo ☀
- Total factura estimada

El selector de mes es un dropdown (`MM/YYYY — Total X €`) que, al cambiar y
enviar el formulario sin confirmar, re-renderiza los campos read-only con los
valores del nuevo mes. La `description` del paso es sólo un texto guía; los
números viven siempre en los campos del formulario, por lo que se ven aunque
el frontend no renderice placeholders markdown.

Además, el usuario puede elegir la fecha `apply_from` desde la que recalcular
las facturas, lo que dispara una re-importación selectiva al confirmar.

### Paso `formulas`

Se permiten plantillas Jinja2 para:

- término de energía
- término de potencia
- otros costes
- término de excedente

El flujo elimina las llaves `{{ }}` antes de guardar el valor, por lo que internamente se persiste la expresión desnuda.

### Paso `confirm`

Simula la última mensualidad disponible y pide fecha desde la que recalcular facturación.

## Entidades expuestas por la integración

### Sensores de información

- `info`

El sensor principal conserva compatibilidad histórica y se publica como `sensor.edata_<scups>`.

### Sensores de energía

- `yesterday_kwh`
- `yesterday_surplus_kwh`
- `last_registered_day_kwh`
- `last_registered_day_surplus_kwh`
- `month_kwh`
- `month_surplus_kwh`
- `last_month_kwh`
- `last_month_surplus_kwh`

Estos sensores leen atributos ya calculados por la librería `e-data` y expuestos por el coordinador.

### Sensores de potencia

- `max_power_kw`

### Sensores de coste

- `month_eur`
- `last_month_eur`
- `month_surplus_eur`
- `last_month_surplus_eur`

Los sensores de coste por excedente existen en `sensor.py` y el fork ya incluye nombres traducidos para ellos. Sigue siendo recomendable validar su trazabilidad end-to-end con datos reales en Home Assistant.

### Botones

- `soft_reset`
- `import_all_data`
- `force_surplus_reimport`

Estos botones delegan en métodos del coordinador para reparar inconsistencias o forzar una sincronización.

Comportamiento de botones forzados:

- `import_all_data` fuerza recarga del periodo largo (`CACHE_MONTHS_LONG`) y omite límites de caché/rate-limit para asegurar descarga real desde Datadis.
- `force_surplus_reimport` fuerza recarga del periodo corto actual (`CACHE_MONTHS_SHORT`) y sobrescribe datos y estadísticas del periodo recargado (consumo, excedente, coste y maxímetro cuando aplique), preservando histórico anterior.
- Ambos muestran advertencia al usuario mediante notificación persistente de Home Assistant al ejecutarse.

## Device model en Home Assistant

`entity.py` agrupa todas las entidades bajo un único dispositivo por `CUPS`, con:

- `identifiers = (edata, CUPS)`
- nombre visible basado en `scups`
- versión software obtenida de la metadata de integración cargada por HA

## Traducciones

Las traducciones disponibles son:

- español (`es.json`)
- inglés (`en.json`)
- catalán (`ca.json`)
- gallego (`gl.json`)

Las cadenas de excedentes ya están presentes en los cuatro idiomas para buena parte de la UI.

## Servicios

Existe `services.yaml` con una definición `recreate_statistics`, pero no se ha encontrado en el código actual un registro de servicio asociado. A efectos de mantenimiento, debe tratarse como superficie pendiente o legado no conectado.