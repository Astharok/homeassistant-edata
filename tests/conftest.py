"""pytest configuration: mock all homeassistant and edata library imports
so that the coordinator module can be imported without a full HA installation.

Only the attributes actually used by the tested methods need to exist on the
mocks; everything else can be a MagicMock sentinel.
"""

from __future__ import annotations

import os as _os
import sys
import types
from unittest.mock import MagicMock


def _make_module(name: str, **attrs) -> types.ModuleType:
    """Create a fake module with the given attributes."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# ------------------------------------------------------------------
# homeassistant stubs
# ------------------------------------------------------------------

# Root
_ha = _make_module("homeassistant")

# homeassistant.components
_ha_comp = _make_module("homeassistant.components")
_ha_comp_pn = _make_module(
    "homeassistant.components.persistent_notification",
    async_create=MagicMock(),
    async_dismiss=MagicMock(),
)
_ha_comp_rec = _make_module("homeassistant.components.recorder")
_ha_comp_rec_db = _make_module(
    "homeassistant.components.recorder.db_schema",
    Statistics=MagicMock(),
)
_ha_comp_rec_models = _make_module(
    "homeassistant.components.recorder.models",
    StatisticData=MagicMock(),
    StatisticMeanType=MagicMock(),
    StatisticMetaData=MagicMock(),
)
_ha_comp_rec_stats = _make_module(
    "homeassistant.components.recorder.statistics",
    async_add_external_statistics=MagicMock(),
    async_import_statistics=MagicMock(),
    get_last_statistics=MagicMock(),
    statistics_during_period=MagicMock(),
    async_list_statistic_ids=MagicMock(),
    list_statistic_ids=MagicMock(),
    get_metadata=MagicMock(),
    clear_statistics=MagicMock(),
)

# homeassistant.config_entries
_ha_ce = _make_module("homeassistant.config_entries", ConfigEntry=MagicMock())

# homeassistant.const
_ha_const = _make_module(
    "homeassistant.const",
    CONF_PASSWORD="password",
    CONF_USERNAME="username",
    STATE_UNAVAILABLE="unavailable",
    CURRENCY_EURO="EUR",
    MAJOR_VERSION=2025,
    MINOR_VERSION=1,
    UnitOfEnergy=MagicMock(),
    UnitOfPower=MagicMock(),
)

# homeassistant.core
_ha_core = _make_module("homeassistant.core", HomeAssistant=MagicMock())

# homeassistant.helpers
_ha_helpers = _make_module("homeassistant.helpers")
_ha_helpers_storage = _make_module(
    "homeassistant.helpers.storage",
    STORAGE_DIR=".storage",
)
_ha_helpers_uc = _make_module(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=object,  # base class — must be real enough to subclass
)

# homeassistant.util
_ha_util = _make_module("homeassistant.util")
_ha_util_dt = _make_module(
    "homeassistant.util.dt",
    as_utc=MagicMock(side_effect=lambda dt: dt),
    now=MagicMock(),
)

# ------------------------------------------------------------------
# edata library stubs
# ------------------------------------------------------------------

_edata = _make_module("edata")
_edata_const = _make_module("edata.const", PROG_NAME="edata")
_edata_def = _make_module(
    "edata.definitions",
    ATTRIBUTES={},
    PricingRules=MagicMock(),
)
_edata_helpers = _make_module("edata.helpers", EdataHelper=MagicMock())
_edata_storage = _make_module("edata.storage", dump_storage=MagicMock())
_edata_proc = _make_module("edata.processors")
_edata_proc_utils = _make_module(
    "edata.processors.utils",
    get_pvpc_tariff=MagicMock(return_value="p1"),
)

# ------------------------------------------------------------------
# custom_components.edata sub-modules used transitively
# ------------------------------------------------------------------

_cc = _make_module("custom_components")
_cc.__path__ = []

_edata_pkg_path = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "custom_components", "edata",
)
_cc_edata = _make_module("custom_components.edata")
_cc_edata.__path__ = [_edata_pkg_path]  # real path so coordinator.py can be found

# const — only the values coordinator.py actually reads at module level
_cc_edata_const = _make_module(
    "custom_components.edata.const",
    DOMAIN="edata",
    CONF_SCUPS="scups",
    CONF_CUPS="cups",
    DATA_STATE="state",
    DATA_ATTRIBUTES="attributes",
    STATE_LOADING="loading",
    CACHE_MONTHS_SHORT=13,
    CACHE_MONTHS_LONG=23,
    COORDINATOR_ID=lambda x: f"edata_{x}",
    STAT_ID_KWH=lambda x: f"edata:{x}_consumption",
    STAT_ID_P1_KWH=lambda x: f"edata:{x}_p1_consumption",
    STAT_ID_P2_KWH=lambda x: f"edata:{x}_p2_consumption",
    STAT_ID_P3_KWH=lambda x: f"edata:{x}_p3_consumption",
    STAT_ID_SURP_KWH=lambda x: f"edata:{x}_surplus",
    STAT_ID_EUR=lambda x: f"edata:{x}_cost",
    STAT_ID_P1_EUR=lambda x: f"edata:{x}_p1_cost",
    STAT_ID_P2_EUR=lambda x: f"edata:{x}_p2_cost",
    STAT_ID_P3_EUR=lambda x: f"edata:{x}_p3_cost",
    STAT_ID_POWER_EUR=lambda x: f"edata:{x}_power_cost",
    STAT_ID_ENERGY_EUR=lambda x: f"edata:{x}_energy_cost",
    STAT_ID_P1_ENERGY_EUR=lambda x: f"edata:{x}_p1_energy_cost",
    STAT_ID_P2_ENERGY_EUR=lambda x: f"edata:{x}_p2_energy_cost",
    STAT_ID_P3_ENERGY_EUR=lambda x: f"edata:{x}_p3_energy_cost",
    STAT_ID_SURPLUS_EUR=lambda x: f"edata:{x}_surplus_cost",
    STAT_ID_MAXIMETER=lambda x: f"edata:{x}_maximeter",
    STAT_ID_P1_MAXIMETER=lambda x: f"edata:{x}_p1_maximeter",
    STAT_ID_P2_MAXIMETER=lambda x: f"edata:{x}_p2_maximeter",
)

_cc_edata_migrate = _make_module(
    "custom_components.edata.migrate",
    migrate_pre2024_storage_if_needed=MagicMock(),
)
_cc_edata_utils = _make_module(
    "custom_components.edata.utils",
    get_db_instance=MagicMock(),
    get_pvpc_tariff=MagicMock(return_value="p1"),
)
_cc_edata_schemas = _make_module("custom_components.edata.schemas")
