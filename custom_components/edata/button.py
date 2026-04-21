"""Button platform for edata component."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant

from . import const
from .entity import EdataButtonEntity


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Set up entry."""
    hass.data.setdefault(const.DOMAIN, {})

    # get configured parameters
    scups = config_entry.data[const.CONF_SCUPS]
    coordinator = hass.data[const.DOMAIN][scups.lower()]["coordinator"]
    # add sensor entities
    _entities = []
    _entities.append(
        EdataResetButton(coordinator, "soft_reset", coordinator.async_soft_reset)
    )
    _entities.append(
        EdataImportButton(coordinator, "import_all_data", coordinator.async_full_import)
    )
    _entities.append(
        EdataForceSurplusReimportButton(
            coordinator,
            "force_surplus_reimport",
            coordinator.async_force_surplus_reimport,
        )
    )
    async_add_entities(_entities)

    return True


class EdataResetButton(EdataButtonEntity, ButtonEntity):
    """Representation of an e-data restoration button."""

    _attr_icon = "mdi:sync-alert"


class EdataImportButton(EdataButtonEntity, ButtonEntity):
    """Representation of an e-data import button."""

    _attr_icon = "mdi:content-save-all"


class EdataForceSurplusReimportButton(EdataButtonEntity, ButtonEntity):
    """Representation of an e-data force surplus reimport button."""

    _attr_icon = "mdi:solar-power-variant"
