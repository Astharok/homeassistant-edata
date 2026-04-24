"""Configuration Schemas."""

import typing

import voluptuous as vol

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector as sel

from . import const

STEP_USER = {
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Optional(const.CONF_AUTHORIZEDNIF): str,
}


def STEP_CHOOSECUPS(cups_list: list[str]) -> dict[str, typing.Any]:
    """Build the dict schema from a cups list."""

    return {
        vol.Required(
            const.CONF_CUPS,
        ): sel.SelectSelector({"options": cups_list}),
    }


def OPTIONS_STEP_INIT(prev_options: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """Build the options init step dict schema."""

    return {
        vol.Required(
            const.CONF_DEBUG,
            default=prev_options.get(const.CONF_DEBUG, False),
        ): bool,
        vol.Required(
            const.CONF_BILLING,
            default=prev_options.get(const.CONF_BILLING, False),
        ): bool,
        vol.Required(
            const.CONF_PVPC,
            default=prev_options.get(const.CONF_PVPC, False),
        ): bool,
        vol.Required(
            const.CONF_SURPLUS,
            default=prev_options.get(const.CONF_SURPLUS, False),
        ): bool,
    }


def OPTIONS_STEP_COSTS(
    is_pvpc: bool, is_surplus: bool, prev_options: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    """Build the options costs step dict schema."""

    effective_surplus = is_surplus and not is_pvpc

    base_schema = {
        vol.Required(
            const.PRICE_P1_KW_YEAR,
            default=prev_options.get(
                const.PRICE_P1_KW_YEAR, const.DEFAULT_PRICE_P1_KW_YEAR
            ),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            const.PRICE_P2_KW_YEAR,
            default=prev_options.get(
                const.PRICE_P2_KW_YEAR, const.DEFAULT_PRICE_P2_KW_YEAR
            ),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            const.PRICE_METER_MONTH,
            default=prev_options.get(
                const.PRICE_METER_MONTH, const.DEFAULT_PRICE_METER_MONTH
            ),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            const.PRICE_ELECTRICITY_TAX,
            default=prev_options.get(
                const.PRICE_ELECTRICITY_TAX,
                const.DEFAULT_PRICE_ELECTRICITY_TAX,
            ),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            const.PRICE_IVA_TAX,
            default=prev_options.get(
                const.PRICE_IVA_TAX,
                const.DEFAULT_PRICE_IVA,
            ),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
    }

    pvpc_schema = {
        vol.Required(
            const.PRICE_MARKET_KW_YEAR,
            default=prev_options.get(
                const.PRICE_MARKET_KW_YEAR,
                const.DEFAULT_PRICE_MARKET_KW_YEAR,
            ),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
    }

    nonpvpc_schema = {
        vol.Required(
            const.PRICE_P1_KWH,
            default=prev_options.get(const.PRICE_P1_KWH, const.DEFAULT_PRICE_P1_KWH),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            const.PRICE_P2_KWH,
            default=prev_options.get(const.PRICE_P2_KWH, const.DEFAULT_PRICE_P2_KWH),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            const.PRICE_P3_KWH,
            default=prev_options.get(const.PRICE_P3_KWH, const.DEFAULT_PRICE_P3_KWH),
        ): sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        ),
    }

    schema = base_schema
    if is_pvpc:
        schema.update(pvpc_schema)
    else:
        schema.update(nonpvpc_schema)
        
    if effective_surplus:
        schema.update({
            vol.Required(
                const.PRICE_SURP_P1_KWH,
                default=prev_options.get(const.PRICE_SURP_P1_KWH, const.DEFAULT_PRICE_SURPLUS_KWH),
            ): sel.NumberSelector(
                config=sel.NumberSelectorConfig(
                    min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
                )
            ),
        })

    return schema


def OPTIONS_STEP_FORMULAS(
    is_pvpc: bool, prev_options: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    """Build the options formulas step dict schema."""

    _text = sel.TextSelector(config=sel.TextSelectorConfig(multiline=False))

    if is_pvpc:
        def_formulas = const.DEFAULT_PVPC_BILLING_FORMULAS
    else:
        def_formulas = const.DEFAULT_CUSTOM_BILLING_FORMULAS

    if (prev_options.get(const.CONF_PVPC, False) != is_pvpc) or not prev_options.get(
        const.CONF_BILLING, False
    ):
        return {
            vol.Required(
                const.BILLING_ENERGY_FORMULA,
                default=def_formulas[const.BILLING_ENERGY_FORMULA],
            ): _text,
            vol.Required(
                const.BILLING_POWER_FORMULA,
                default=def_formulas[const.BILLING_POWER_FORMULA],
            ): _text,
            vol.Required(
                const.BILLING_OTHERS_FORMULA,
                default=def_formulas[const.BILLING_OTHERS_FORMULA],
            ): _text,
            vol.Required(
                const.BILLING_SURPLUS_FORMULA,
                default=def_formulas.get(const.BILLING_SURPLUS_FORMULA),
            ): _text,
        }

    return {
        vol.Required(
            const.BILLING_ENERGY_FORMULA,
            default=prev_options.get(
                const.BILLING_ENERGY_FORMULA,
                def_formulas[const.BILLING_ENERGY_FORMULA],
            ),
        ): _text,
        vol.Required(
            const.BILLING_POWER_FORMULA,
            default=prev_options.get(
                const.BILLING_POWER_FORMULA,
                def_formulas[const.BILLING_POWER_FORMULA],
            ),
        ): _text,
        vol.Required(
            const.BILLING_OTHERS_FORMULA,
            default=prev_options.get(
                const.BILLING_OTHERS_FORMULA,
                def_formulas[const.BILLING_OTHERS_FORMULA],
            ),
        ): _text,
        vol.Required(
            const.BILLING_SURPLUS_FORMULA,
            default=prev_options.get(
                const.BILLING_SURPLUS_FORMULA,
                def_formulas[const.BILLING_SURPLUS_FORMULA],
            ),
        ): _text,
    }


def OPTIONS_STEP_CONFIRM(
    sim: dict | None,
    sim_all: list | None = None,
    apply_from: str | None = None,
) -> dict[str, typing.Any]:
    """Build the options confirm step dict schema.

    Shows a month selector (re-renders on change), a breakdown of all billing
    terms for the selected month, and the apply_from / confirm fields.
    """
    schema: dict = {}

    # Month selector — submitting the form with confirm=False re-renders with
    # the newly selected month's data.
    if sim_all:
        month_options = [
            {
                "value": rec["datetime"].strftime("%Y-%m"),
                "label": rec["datetime"].strftime("%m/%Y"),
            }
            for rec in sim_all
        ]
        selected_month = (
            sim["datetime"].strftime("%Y-%m") if sim else month_options[-1]["value"]
        )
        schema[vol.Required(const.CONF_SIM_MONTH, default=selected_month)] = (
            sel.SelectSelector({"options": month_options, "mode": "dropdown"})
        )

    if sim is not None:
        schema[vol.Required(const.CONF_DELTA_H, default=sim.get("delta_h", 0))] = (
            vol.Coerce(int)
        )
        schema[
            vol.Required(
                const.CONF_ENERGY_TERM,
                default=round(sim.get("energy_term") or 0.0, 4),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                const.CONF_POWER_TERM,
                default=round(sim.get("power_term") or 0.0, 4),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                const.CONF_SURPLUS_TERM,
                default=round(sim.get("surplus_term") or 0.0, 4),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                const.CONF_SAVINGS_TERM,
                default=round(sim.get("savings_term") or 0.0, 4),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                const.CONF_OTHERS_TERM,
                default=round(sim.get("others_term") or 0.0, 4),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                const.CONF_VALUE_EUR,
                default=round(sim.get("value_eur") or 0.0, 4),
            )
        ] = vol.Coerce(float)

    if apply_from:
        schema[vol.Required(const.CONF_APPLYFROM, default=apply_from)] = (
            sel.DateTimeSelector()
        )
    else:
        schema[vol.Required(const.CONF_APPLYFROM)] = sel.DateTimeSelector()

    schema[vol.Required(const.CONF_CONFIRM, default=False)] = bool

    return schema
