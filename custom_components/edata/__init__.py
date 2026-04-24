"""Home Assistant e-data integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
from homeassistant.components import persistent_notification

from . import const, utils
from .coordinator import EdataCoordinator
from .websockets import async_register_websockets

PLATFORMS: list[str] = ["button", "sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up edata-card resources."""

    path = Path(__file__).parent / "www"
    name = "edata-card.js"
    utils.register_static_path(hass.http.app, "/edata/" + name, path / name)
    version = getattr(hass.data["integrations"][const.DOMAIN], "version", 0)
    await utils.init_resource(hass, "/edata/edata-card.js", str(version))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up edata from a config entry."""
    _LOGGER.debug("Setting up platform 'edata'")

    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    entry.async_on_unload(unsub_options_update_listener)

    hass.data.setdefault(const.DOMAIN, {})

    # get configured parameters
    usr = entry.data[CONF_USERNAME]
    pwd = entry.data[CONF_PASSWORD]
    cups = entry.data[const.CONF_CUPS]
    authorized_nif = entry.data.get(const.CONF_AUTHORIZEDNIF, None)
    scups = entry.data[const.CONF_SCUPS]
    billing_enabled = entry.options.get(const.CONF_BILLING, False)
    component_logger = logging.getLogger(f"custom_components.{const.DOMAIN}")

    if entry.options.get(const.CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.DEBUG)
        component_logger.setLevel(logging.DEBUG)
        _LOGGER.info("%s: debug logging enabled (level=DEBUG for edata + custom_components.edata)", scups)
    else:
        logging.getLogger("edata").setLevel(logging.WARNING)
        component_logger.setLevel(logging.WARNING)

    if billing_enabled:
        pricing_rules = {
            const.PRICE_ELECTRICITY_TAX: const.DEFAULT_PRICE_ELECTRICITY_TAX,
            const.PRICE_IVA_TAX: const.DEFAULT_PRICE_IVA,
        }
        pricing_rules.update(
            {
                x: entry.options[x]
                for x in entry.options
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
        )
        # Mirror single surplus price across all 3 periods (UI only asks for P1;
        # BillingProcessor expects all 3 in PricingRules).
        _surp_p1 = pricing_rules.get(const.PRICE_SURP_P1_KWH)
        if _surp_p1 is not None:
            pricing_rules[const.PRICE_SURP_P2_KWH] = _surp_p1
            pricing_rules[const.PRICE_SURP_P3_KWH] = _surp_p1

        # Auto-migrate legacy buggy surplus_formula (pre-fix versions suggested
        # formulas that multiplied the compensation by electricity_tax * iva_tax
        # and/or used kwh_eur — the import price — instead of surplus_kwh_eur).
        _orig_surplus = pricing_rules.get(const.BILLING_SURPLUS_FORMULA)
        _migrated_surplus = const.migrate_surplus_formula(
            _orig_surplus, pvpc=bool(entry.options.get(const.CONF_PVPC, False))
        )
        if _migrated_surplus != _orig_surplus:
            pricing_rules[const.BILLING_SURPLUS_FORMULA] = _migrated_surplus
            _LOGGER.warning(
                "%s: auto-migrated legacy surplus_formula %r -> %r "
                "(open Options -> Formulas -> Confirm to persist).",
                scups, _orig_surplus, _migrated_surplus,
            )
            # Signal that a full cost rebuild is needed after first refresh:
            # cost_* arrays persisted on disk still contain values computed
            # with the buggy formula; process_data() does NOT rewrite existing
            # rows, only appends new ones. update_billing(since=None) wipes
            # and recomputes from scratch.
            _force_cost_rebuild = True
            persistent_notification.async_create(
                hass,
                (
                    f"La integración edata ha detectado una fórmula de compensación "
                    f"de excedentes obsoleta y la ha corregido automáticamente.\n\n"
                    f"**Anterior**: `{_orig_surplus}`\n"
                    f"**Nueva**: `{_migrated_surplus}`\n\n"
                    f"La factura histórica (tarjeta edata-card y panel Energía) "
                    f"se está recalculando automáticamente en segundo plano. "
                    f"Cuando termine, abre *Configuración → Dispositivos y "
                    f"servicios → edata → Configurar → Fórmulas → Continuar → "
                    f"Confirmar cambios* para persistir la fórmula corregida "
                    f"en disco."
                ),
                title="edata: fórmula de excedentes corregida",
                notification_id=f"edata_surplus_formula_migrated_{scups}",
            )
        else:
            _force_cost_rebuild = False
    else:
        pricing_rules = None
        _force_cost_rebuild = False

    coordinator = await EdataCoordinator.async_setup(
        hass,
        usr,
        pwd,
        cups,
        scups,
        authorized_nif,
        pricing_rules,
    )
    hass.data[const.DOMAIN][scups.lower()]["coordinator"] = coordinator

    # postpone first refresh to speed up startup
    @callback
    async def async_first_refresh(*args):
        """Force the component to assess the first refresh."""
        await coordinator.async_refresh()
        # If we auto-migrated the surplus formula, existing cost_* rows on disk
        # were computed with the buggy formula. Trigger a full rebuild so the
        # websocket (dashboard) and LTS stats (Energy tab) both reflect the
        # corrected formula across the entire history.
        if _force_cost_rebuild:
            _LOGGER.warning(
                "%s: surplus formula migrated — rebuilding full cost history "
                "so dashboard and Energy tab show corrected values.",
                scups,
            )
            try:
                await coordinator.update_billing(entry.options, since=None)
            except Exception:
                _LOGGER.exception(
                    "%s: forced cost rebuild after surplus migration failed; "
                    "run Options -> Formulas -> Confirm with an old 'Recalcular "
                    "facturas desde...' date to retry manually.",
                    scups,
                )

    if hass.state == CoreState.running:
        hass.async_create_task(async_first_refresh())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, async_first_refresh)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # register websockets
    async_register_websockets(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(const.DOMAIN, {}).pop(entry.data.get("scups"), None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry) -> None:
    """Handle removal of an entry."""

    hass.data.get(const.DOMAIN, {}).pop(entry.data.get("scups"), None)


async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""

    scups = entry.data[const.CONF_SCUPS]
    _LOGGER.debug("%s: options changed", scups)
    data = hass.data[const.DOMAIN][scups.lower()]
    coor: EdataCoordinator = data["coordinator"]

    since_str = entry.options.get("update_billing_since")
    since = dt_util.as_local(dt_util.parse_datetime(since_str)) if since_str else None
    await coor.update_billing(entry.options, since)
