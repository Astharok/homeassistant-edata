"""Configuration Flow (GUI)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from edata.connectors.datadis import DatadisConnector
from edata.definitions import PricingRules
from edata.processors.billing import BillingProcessor
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from . import const, schemas as sch

_LOGGER = logging.getLogger(__name__)

J2_EXPR_TOKENS = ("{{ ", " }}")


class AlreadyConfigured(HomeAssistantError):
    """Error to indicate CUPS is already configured."""


class InvalidCredentials(HomeAssistantError):
    """Error to indicate credentials are invalid."""


class NoSuppliesFound(HomeAssistantError):
    """Error to indicate no supplies were found."""


class InvalidCups(HomeAssistantError):
    """Error to indicate cups is invalid."""


async def test_login(username, password, authorized_nif=None):
    """Test login asynchronously."""

    api = DatadisConnector(username, password)

    api._recent_queries = {}  # noqa: SLF001
    api._recent_cache = {}  # noqa: SLF001

    if await api._async_get_token() is False:
        return None

    return await api.async_get_supplies(authorized_nif=authorized_nif)


def get_scups(hass: HomeAssistant, cups: str) -> str:
    """Calculate a non-colliding scups."""

    for i in range(4, len(cups)):
        scups = cups[-i:].lower()
        found = hass.data.get(const.DOMAIN, {}).get(scups)
        if found is None:
            break
        elif found[const.CONF_CUPS] == cups.upper():  # noqa: RET508
            raise AlreadyConfigured

    return scups


async def validate_step_user(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input from the 'step user'."""

    if data.get(const.CONF_AUTHORIZEDNIF, None) == data[CONF_USERNAME]:
        _LOGGER.warning(
            "Ignoring authorized NIF since it is equal to the provided username"
        )
        data[const.CONF_AUTHORIZEDNIF] = None

    result = await test_login(
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data.get(const.CONF_AUTHORIZEDNIF, None),
    )

    if result is None:
        raise InvalidCredentials

    if not result:
        raise NoSuppliesFound

    return [x["cups"] for x in result]


async def simulate_last_month_billing(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input from the 'step formulas'."""

    coordinator_id = config_entry.data["scups"].lower()

    _LOGGER.warning(
        "simulate_billing: coordinator_id=%s data_keys=%s",
        coordinator_id,
        list(data.keys()),
    )

    pricing_rules_input = {
        x: data[x]
        for x in data
        if x
        in (
            const.CONF_CYCLE_START_DAY,
            const.PRICE_P1_KW_YEAR,
            const.PRICE_P2_KW_YEAR,
            const.PRICE_P1_KWH,
            const.PRICE_P2_KWH,
            const.PRICE_P3_KWH,
            const.PRICE_SURP_P1_KWH,
            const.PRICE_METER_MONTH,
            const.PRICE_MARKET_KW_YEAR,
            const.PRICE_ELECTRICITY_TAX,
            const.PRICE_IVA_TAX,
            const.BILLING_ENERGY_FORMULA,
            const.BILLING_POWER_FORMULA,
            const.BILLING_OTHERS_FORMULA,
            const.BILLING_SURPLUS_FORMULA,
        )
    }
    _LOGGER.warning("simulate_billing: pricing_rules_input=%s", pricing_rules_input)

    try:
        pricing_rules = PricingRules(pricing_rules_input)
        _LOGGER.warning("simulate_billing: PricingRules OK")
    except Exception:
        _LOGGER.exception("simulate_billing: PricingRules() raised")
        raise

    edata_obj = hass.data[const.DOMAIN][coordinator_id]["edata"]
    consumptions = edata_obj.data.get("consumptions", [])
    contracts = edata_obj.data.get("contracts", [])
    pvpc = edata_obj.data.get("pvpc", [])
    _EXTRAS_KEYS = {"generation_kWh", "self_consumption_kWh", "obtain_method"}
    consumptions_clean = [
        {k: v for k, v in rec.items() if k not in _EXTRAS_KEYS}
        for rec in consumptions
    ]
    _LOGGER.warning(
        "simulate_billing: consumptions=%d contracts=%d pvpc=%d",
        len(consumptions_clean),
        len(contracts),
        len(pvpc),
    )

    _bp_input = {
        "consumptions": consumptions_clean,
        "contracts": contracts,
        "prices": pvpc,
        "rules": pricing_rules,
    }
    try:
        proc = await hass.async_add_executor_job(
            BillingProcessor, _bp_input
        )
        _LOGGER.warning(
            "simulate_billing: BillingProcessor OK monthly=%d",
            len(proc.output.get("monthly", [])),
        )
    except Exception:
        _LOGGER.exception("simulate_billing: BillingProcessor() raised")
        raise

    monthly = proc.output.get("monthly", [])

    # --- Compute self-consumption savings via a second BillingProcessor run ---
    # Read sidecar directly so we have sc data even if _apply_extras_sidecar
    # hasn't run yet (coordinator first cycle may not have completed).
    _coordinator = hass.data[const.DOMAIN][coordinator_id].get("coordinator")
    _sidecar_extras: dict = {}
    if _coordinator is not None:
        try:
            _sidecar_extras = await hass.async_add_executor_job(
                _coordinator._read_sidecar_sync
            )
        except Exception:
            _LOGGER.warning("simulate_billing: could not read sidecar, savings_term will be 0")

    _LOGGER.warning(
        "simulate_billing: sidecar entries=%d (coordinator available=%s)",
        len(_sidecar_extras),
        _coordinator is not None,
    )

    # Build consumptions_with_sc: same as consumptions_clean but with
    # self_consumption_kWh added back into the correct period field so that
    # BillingProcessor applies the same per-period energy formula to it.
    _SC_KEYS_SET = {"generation_kWh", "self_consumption_kWh", "obtain_method"}
    consumptions_with_sc = []
    for rec in consumptions:
        # Prefer sidecar (always fresh) over in-memory (may not be enriched yet)
        sc = 0.0
        _rec_dt = rec.get("datetime")
        if _sidecar_extras and _rec_dt is not None:
            _iso = _rec_dt.replace(minute=0, second=0, microsecond=0).isoformat()
            sc = (_sidecar_extras.get(_iso) or {}).get("self_consumption_kWh") or 0.0
        if sc == 0.0:
            sc = rec.get("self_consumption_kWh") or 0.0
        clean = {k: v for k, v in rec.items() if k not in _SC_KEYS_SET}
        if sc > 0:
            if (clean.get("value_p1_kWh") or 0.0) > 0:
                clean["value_p1_kWh"] = (clean.get("value_p1_kWh") or 0.0) + sc
            elif (clean.get("value_p2_kWh") or 0.0) > 0:
                clean["value_p2_kWh"] = (clean.get("value_p2_kWh") or 0.0) + sc
            elif (clean.get("value_p3_kWh") or 0.0) > 0:
                clean["value_p3_kWh"] = (clean.get("value_p3_kWh") or 0.0) + sc
            else:
                # Zero grid consumption (fully covered by solar): period unknown; use P3 as conservative lower bound
                clean["value_p3_kWh"] = (clean.get("value_p3_kWh") or 0.0) + sc
            clean["value_kWh"] = (clean.get("value_kWh") or 0.0) + sc
        consumptions_with_sc.append(clean)

    monthly_sc = []
    _bp_sc_input = {
        "consumptions": consumptions_with_sc,
        "contracts": contracts,
        "prices": pvpc,
        "rules": pricing_rules,
    }
    try:
        proc_sc = await hass.async_add_executor_job(BillingProcessor, _bp_sc_input)
        monthly_sc = proc_sc.output.get("monthly", [])
        _LOGGER.warning("simulate_billing: BillingProcessor (sc) OK monthly=%d", len(monthly_sc))
    except Exception:
        _LOGGER.exception("simulate_billing: BillingProcessor (sc) raised — savings_term will be 0")

    savings_map = {
        rec_sc["datetime"]: (rec_sc.get("energy_term") or 0.0)
        for rec_sc in monthly_sc
    }
    for rec in monthly:
        actual_energy = rec.get("energy_term") or 0.0
        sc_energy = savings_map.get(rec["datetime"])
        rec["savings_term"] = round(
            (sc_energy - actual_energy) if sc_energy is not None else 0.0, 4
        )

    for i, rec in enumerate(monthly):
        _LOGGER.warning(
            "simulate_billing: [%d] %s delta_h=%d energy=%.4f power=%.4f surplus=%.4f others=%.4f savings=%.4f total=%.4f",
            i,
            rec["datetime"].strftime("%m/%Y"),
            rec.get("delta_h", 0),
            rec.get("energy_term") or 0,
            rec.get("power_term") or 0,
            rec.get("surplus_term") or 0,
            rec.get("others_term") or 0,
            rec.get("savings_term") or 0,
            rec.get("value_eur") or 0,
        )
    if not monthly:
        _LOGGER.warning("simulate_billing: no monthly records (normal after switching to PVPC)")
    return monthly


class ConfigFlow(config_entries.ConfigFlow, domain=const.DOMAIN):
    """Handle a config flow for edata."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        super().__init__()
        self.inputs = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=vol.Schema(sch.STEP_USER)
            )

        errors = {}

        try:
            self.inputs["cups_list"] = await validate_step_user(self.hass, user_input)
        except InvalidCredentials:
            errors["base"] = "invalid_credentials"
        except NoSuppliesFound:
            errors["base"] = "no_supplies_found"
        except Exception as e:
            _LOGGER.exception(e)
        else:
            self.inputs.update(user_input)
            return await self.async_step_choosecups()

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(sch.STEP_USER), errors=errors
        )

    async def async_step_choosecups(self, user_input=None) -> FlowResult:
        """Handle the 'choose cups' step."""

        if user_input is not None:
            self.inputs.update(user_input)
            try:
                self.inputs[const.CONF_SCUPS] = get_scups(
                    self.hass, self.inputs[const.CONF_CUPS]
                )
            except AlreadyConfigured:
                return self.async_show_form(
                    step_id="choosecups",
                    data_schema=vol.Schema(
                        sch.STEP_CHOOSECUPS(self.inputs["cups_list"])
                    ),
                    errors={"base": "already_configured"},
                )
            except Exception as e:
                _LOGGER.exception(e)

            return self.async_create_entry(
                title=self.inputs[const.CONF_SCUPS],
                data={**self.inputs},
            )

        return self.async_show_form(
            step_id="choosecups",
            data_schema=vol.Schema(sch.STEP_CHOOSECUPS(self.inputs["cups_list"])),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlowHandler:
        """Return the options flow handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Provide options for edata."""

    def __init__(self) -> None:
        """Initialize options flow."""
        super().__init__()
        self.inputs = {}
        self.sim: dict | None = {}
        self.sim_all: list = []
        self._confirm_apply_from: str | None = None

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            if not user_input[const.CONF_BILLING]:
                return self.async_create_entry(
                    title="",
                    data=user_input,
                )
            self.inputs = user_input
            try:
                return await self.async_step_costs()
            except Exception as e:
                _LOGGER.exception(e)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(sch.OPTIONS_STEP_INIT(self.config_entry.options)),
        )

    async def async_step_costs(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            if const.PRICE_MARKET_KW_YEAR not in user_input:
                user_input[const.PRICE_MARKET_KW_YEAR] = (
                    const.DEFAULT_PRICE_MARKET_KW_YEAR
                )
            for key in user_input:
                self.inputs[key] = user_input[key]

            try:
                return await self.async_step_formulas()
            except Exception as e:
                _LOGGER.exception(e)

        return self.async_show_form(
            step_id="costs",
            data_schema=vol.Schema(
                sch.OPTIONS_STEP_COSTS(
                    self.inputs[const.CONF_PVPC], self.inputs[const.CONF_SURPLUS], self.config_entry.options
                )
            ),
        )

    async def async_step_formulas(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:

            for key in user_input:
                # Strip any accidental {{ }} wrapping (legacy TemplateSelector values)
                self.inputs[key] = (
                    user_input[key]
                    .replace(J2_EXPR_TOKENS[0].strip(), "")
                    .replace(J2_EXPR_TOKENS[1].strip(), "")
                    .strip()
                )
            _LOGGER.warning(
                "async_step_formulas: user_input received keys=%s stripped_values=%s",
                list(user_input.keys()),
                {k: self.inputs[k] for k in user_input},
            )
            try:
                all_months = await simulate_last_month_billing(
                    self.hass, self.config_entry, self.inputs
                )
                self.sim_all = all_months or []
                if len(self.sim_all) > 1:
                    self.sim = self.sim_all[-2]
                elif self.sim_all:
                    self.sim = self.sim_all[-1]
                else:
                    self.sim = None
                _LOGGER.warning(
                    "async_step_formulas: simulation OK months=%d selected=%s",
                    len(self.sim_all),
                    self.sim.get("datetime") if self.sim else None,
                )
            except Exception as e:
                _LOGGER.exception("async_step_formulas: simulate_last_month_billing raised: %s", e)
                raise
            try:
                return await self.async_step_confirm()
            except Exception as e:
                _LOGGER.exception("async_step_formulas: async_step_confirm raised: %s", e)
                raise

        return self.async_show_form(
            step_id="formulas",
            data_schema=vol.Schema(
                sch.OPTIONS_STEP_FORMULAS(
                    self.inputs[const.CONF_PVPC], self.config_entry.options
                )
            ),
        )

    async def async_step_confirm(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            if "apply_from" in user_input:
                self._confirm_apply_from = user_input["apply_from"]

            if user_input.get(const.CONF_CONFIRM, False):
                self.inputs["update_billing_since"] = user_input["apply_from"]
                return self.async_create_entry(title="", data=self.inputs)

            # Month selector changed: re-render with the selected month's data
            selected = user_input.get(const.CONF_SIM_MONTH)
            if selected and self.sim_all:
                for rec in self.sim_all:
                    if rec["datetime"].strftime("%Y-%m") == selected:
                        self.sim = rec
                        break

        def _fmt(v, decimals=2):
            if v is None:
                return "—"
            return f"{float(v):.{decimals}f}"

        sim = self.sim or {}
        placeholders = {
            "month": sim.get("datetime").strftime("%m/%Y") if sim.get("datetime") else "—",
            "delta_h": str(sim.get("delta_h", 0)),
            "energy_term": _fmt(sim.get("energy_term")),
            "power_term": _fmt(sim.get("power_term")),
            "surplus_term": _fmt(sim.get("surplus_term")),
            "savings_term": _fmt(sim.get("savings_term")),
            "others_term": _fmt(sim.get("others_term")),
            "value_eur": _fmt(sim.get("value_eur")),
        }

        _LOGGER.warning(
            "async_step_confirm: showing form sim=%s sim_all=%d placeholders=%s",
            bool(sim),
            len(self.sim_all or []),
            {k: v for k, v in placeholders.items() if k in ("month", "value_eur", "savings_term")},
        )

        try:
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema(
                    sch.OPTIONS_STEP_CONFIRM(self.sim, self.sim_all, self._confirm_apply_from)
                ),
                description_placeholders=placeholders,
            )
        except Exception:
            _LOGGER.exception("async_step_confirm: async_show_form raised — showing form without placeholders")
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema(
                    sch.OPTIONS_STEP_CONFIRM(self.sim, self.sim_all, self._confirm_apply_from)
                ),
            )
