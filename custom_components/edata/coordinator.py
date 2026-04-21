"""Data update coordinator definitions."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
import glob
import json
import logging
import math
import os

from dateutil.relativedelta import relativedelta

from edata.const import PROG_NAME as EDATA_PROG_NAME
from edata.definitions import ATTRIBUTES, PricingRules
from edata.helpers import EdataHelper
from edata.processors import utils
from homeassistant.components import persistent_notification
from homeassistant.components.recorder.db_schema import Statistics
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    get_metadata,
    list_statistic_ids,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CURRENCY_EURO,
    MAJOR_VERSION,
    MINOR_VERSION,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .migrate import migrate_pre2024_storage_if_needed
from .utils import get_db_instance

_LOGGER = logging.getLogger(__name__)


class EdataCoordinator(DataUpdateCoordinator):
    """Handle Datadis data and statistics.."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        scups: str,
        authorized_nif: str,
        billing: PricingRules | None = None,
    ) -> None:
        """Initialize the data handler.."""

        # Number of cached months (starting from 1st day of the month will be automatic)
        self.cache_months = const.CACHE_MONTHS_SHORT

        # Store properties
        self.hass = hass
        self.cups = cups.upper()
        self.authorized_nif = authorized_nif
        self.scups = scups.upper()
        self.id = scups.lower()
        self.billing_rules = billing

        # Check if v2023 storage has already been migrated
        migrate_pre2024_storage_if_needed(hass, self.cups, self.id)

        # Init shared data
        hass.data[const.DOMAIN][self.id] = {const.CONF_CUPS: self.cups}

        # Instantiate the api helper
        self._edata = EdataHelper(
            username,
            password,
            self.cups,
            self.authorized_nif,
            pricing_rules=self.billing_rules,
            storage_dir_path=self.hass.config.path(STORAGE_DIR),
        )

        # Making self._data to reference hass.data[const.DOMAIN][self.id] so we can use it like an alias
        self._data = hass.data[const.DOMAIN][self.id]
        self._data[EDATA_PROG_NAME] = self._edata
        self._data.update(
            {
                const.DATA_STATE: const.STATE_LOADING,
                const.DATA_ATTRIBUTES: {x: None for x in ATTRIBUTES},
            }
        )

        # self._load_data(preprocess=True)

        # Used statistic IDs (edata:<id>_metric_to_track)
        self.statistic_ids = {
            const.STAT_ID_KWH(self.id),
            const.STAT_ID_P1_KWH(self.id),
            const.STAT_ID_P2_KWH(self.id),
            const.STAT_ID_P3_KWH(self.id),
            const.STAT_ID_SURP_KWH(self.id),
            const.STAT_ID_KW(self.id),
            const.STAT_ID_P1_KW(self.id),
            const.STAT_ID_P2_KW(self.id),
        }

        if self.billing_rules:
            # If billing rules are provided, we also track costs
            self.statistic_ids.update(
                {
                    const.STAT_ID_EUR(self.id),
                    const.STAT_ID_P1_EUR(self.id),
                    const.STAT_ID_P2_EUR(self.id),
                    const.STAT_ID_P3_EUR(self.id),
                    const.STAT_ID_POWER_EUR(self.id),
                    const.STAT_ID_ENERGY_EUR(self.id),
                    const.STAT_ID_P1_ENERGY_EUR(self.id),
                    const.STAT_ID_P2_ENERGY_EUR(self.id),
                    const.STAT_ID_P3_ENERGY_EUR(self.id),
                    const.STAT_ID_SURPLUS_EUR(self.id),
                }
            )

        # Stats id grouped by scope

        self.consumptions_stat_ids = {
            const.STAT_ID_KWH(self.id),
            const.STAT_ID_P1_KWH(self.id),
            const.STAT_ID_P2_KWH(self.id),
            const.STAT_ID_P3_KWH(self.id),
        }

        self.surplus_stat_ids = {
            const.STAT_ID_SURP_KWH(self.id),
        }

        self.energy_stat_ids = self.consumptions_stat_ids.union(self.surplus_stat_ids)

        self.maximeter_stat_ids = {
            const.STAT_ID_KW(self.id),
            const.STAT_ID_P1_KW(self.id),
            const.STAT_ID_P2_KW(self.id),
        }

        self.cost_stat_ids = {
            const.STAT_ID_EUR(self.id),
            const.STAT_ID_P1_EUR(self.id),
            const.STAT_ID_P2_EUR(self.id),
            const.STAT_ID_P3_EUR(self.id),
            const.STAT_ID_POWER_EUR(self.id),
            const.STAT_ID_ENERGY_EUR(self.id),
            const.STAT_ID_P1_ENERGY_EUR(self.id),
            const.STAT_ID_P2_ENERGY_EUR(self.id),
            const.STAT_ID_P3_ENERGY_EUR(self.id),
            const.STAT_ID_SURPLUS_EUR(self.id),
        }

        # We also track last stats sum and datetime
        self._last_stats_sum = None
        self._last_stats_dt = None
        self._corrupt_stats = []

        # Manual import diagnostics (for rate-limit awareness).
        self._full_import_calls = 0
        self._full_import_last_run: datetime | None = None

        hass.data[const.DOMAIN][self.id]["dt_last"] = self._last_stats_dt

        # Just the preamble of the statistics
        self._stat_id_preamble = f"{const.DOMAIN}:{self.id}"

        super().__init__(
            hass,
            _LOGGER,
            name=const.COORDINATOR_ID(self.id),
            update_interval=timedelta(minutes=60),
        )

    @classmethod
    async def async_setup(
        cls,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        scups: str,
        authorized_nif: str,
        billing: PricingRules | None = None,
    ):
        """Async constructor."""

        return await hass.async_add_executor_job(
            cls, hass, username, password, cups, scups, authorized_nif, billing
        )

    async def _async_update_data(self, update_statistics=True):
        """Update data via API."""

        date_from = datetime.today().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) - relativedelta(months=self.cache_months)
        date_to = datetime.today().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(minutes=1)

        _LOGGER.warning(
            "%s: update requested cache_months=%s from=%s to=%s",
            self.scups,
            self.cache_months,
            date_from.isoformat(),
            date_to.isoformat(),
        )

        pre_counts = {
            "supplies": len(self._edata.data.get("supplies", [])),
            "contracts": len(self._edata.data.get("contracts", [])),
            "consumptions": len(self._edata.data.get("consumptions", [])),
            "maximeter": len(self._edata.data.get("maximeter", [])),
            "pvpc": len(self._edata.data.get("pvpc", [])),
            "cost_hourly_sum": len(self._edata.data.get("cost_hourly_sum", [])),
        }
        _LOGGER.warning("%s: update pre-counts %s", self.scups, pre_counts)

        if isinstance(self._edata.last_update, dict):
            _LOGGER.warning(
                "%s: update last_update pre supplies=%s contracts=%s consumptions=%s maximeter=%s pvpc=%s",
                self.scups,
                self._edata.last_update.get("supplies"),
                self._edata.last_update.get("contracts"),
                self._edata.last_update.get("consumptions"),
                self._edata.last_update.get("maximeter"),
                self._edata.last_update.get("pvpc"),
            )

        _LOGGER.warning(
            "%s: update invoking edata helper cups=%s authorized_nif=%s billing=%s",
            self.scups,
            self.cups,
            bool(self.authorized_nif),
            self.billing_rules is not None,
        )

        # Run the update in a worker and wait for completion before continuing.
        # e-data's async wrapper can return before the underlying update is done.
        update_result = await asyncio.to_thread(
            self._edata.update,
            date_from,
            date_to,
        )
        _LOGGER.warning("%s: update helper returned %s", self.scups, update_result)

        post_counts = {
            "supplies": len(self._edata.data.get("supplies", [])),
            "contracts": len(self._edata.data.get("contracts", [])),
            "consumptions": len(self._edata.data.get("consumptions", [])),
            "maximeter": len(self._edata.data.get("maximeter", [])),
            "pvpc": len(self._edata.data.get("pvpc", [])),
            "cost_hourly_sum": len(self._edata.data.get("cost_hourly_sum", [])),
        }
        _LOGGER.warning("%s: update post-counts %s", self.scups, post_counts)

        if isinstance(self._edata.last_update, dict):
            _LOGGER.warning(
                "%s: update last_update post supplies=%s contracts=%s consumptions=%s maximeter=%s pvpc=%s",
                self.scups,
                self._edata.last_update.get("supplies"),
                self._edata.last_update.get("contracts"),
                self._edata.last_update.get("consumptions"),
                self._edata.last_update.get("maximeter"),
                self._edata.last_update.get("pvpc"),
            )

        if self._edata.data.get("supplies"):
            _LOGGER.warning(
                "%s: update supplies sample cups=%s date_start=%s date_end=%s",
                self.scups,
                self._edata.data["supplies"][0].get("cups"),
                self._edata.data["supplies"][0].get("date_start"),
                self._edata.data["supplies"][0].get("date_end"),
            )
        else:
            _LOGGER.warning("%s: update got zero supplies", self.scups)

        if self._edata.data.get("contracts"):
            _LOGGER.warning(
                "%s: update contracts sample marketer=%s date_start=%s date_end=%s",
                self.scups,
                self._edata.data["contracts"][0].get("marketer"),
                self._edata.data["contracts"][0].get("date_start"),
                self._edata.data["contracts"][0].get("date_end"),
            )
        else:
            _LOGGER.warning("%s: update got zero contracts", self.scups)

        if self._edata.data.get("consumptions"):
            first = self._edata.data["consumptions"][0]
            last = self._edata.data["consumptions"][-1]
            _LOGGER.warning(
                "%s: update consumptions sample first=%s last=%s first_value=%s first_surplus=%s",
                self.scups,
                first.get("datetime"),
                last.get("datetime"),
                first.get("value_kWh"),
                first.get("surplus_kWh"),
            )
        else:
            _LOGGER.warning("%s: update got zero consumptions", self.scups)
        self._log_refresh_summary()

        if update_statistics:
            await self.update_statistics()

        await self._load_data()

        return self._data

    def _log_refresh_summary(self):
        """Log a compact data summary to validate downloaded payloads."""

        if not _LOGGER.isEnabledFor(logging.INFO):
            return

        consumptions = self._edata.data.get("consumptions", [])
        costs = self._edata.data.get("cost_hourly_sum", [])
        maximeter = self._edata.data.get("maximeter", [])
        surplus_nonzero = 0
        surplus_total = 0.0

        start_dt = None
        end_dt = None
        if consumptions:
            start_dt = consumptions[0].get("datetime")
            end_dt = consumptions[-1].get("datetime")
            surplus_values = [x.get("surplus_kWh", 0) or 0 for x in consumptions]
            surplus_nonzero = sum(1 for x in surplus_values if x > 0)
            surplus_total = sum(surplus_values)

        _LOGGER.info(
            "%s: refresh summary consumptions=%d costs=%d maximeter=%d surplus_nonzero=%d surplus_total=%.3f range=%s..%s",
            self.scups,
            len(consumptions),
            len(costs),
            len(maximeter),
            surplus_nonzero,
            surplus_total,
            start_dt,
            end_dt,
        )

    async def _load_data(self, preprocess=False):
        """Load data found in built-in statistics into state, attributes and websockets."""

        try:
            if preprocess:
                await asyncio.to_thread(self._edata.process_data)

            # reference to attributes shared storage
            attrs = self._data[const.DATA_ATTRIBUTES]
            attrs.update(self._edata.attributes)
            attrs["import_all_data_calls"] = self._full_import_calls
            attrs["import_all_data_last_run"] = (
                None
                if self._full_import_last_run is None
                else self._full_import_last_run.isoformat()
            )

            # load into websockets
            self._data[const.WS_CONSUMPTIONS_DAY] = self._edata.data[
                "consumptions_daily_sum"
            ]
            self._data[const.WS_CONSUMPTIONS_MONTH] = self._edata.data[
                "consumptions_monthly_sum"
            ]
            self._data["ws_maximeter"] = self._edata.data["maximeter"]

            # update state
            with contextlib.suppress(AttributeError):
                self._data["state"] = self._edata.attributes[
                    "last_registered_date"
                ].strftime("%d/%m/%Y")

        except Exception:
            _LOGGER.warning("Some data is missing, will try to fetch later")
            return False

        return True

    async def _update_last_stats_summary(self):
        """Update self._last_stats_sum and self._last_stats_dt."""

        _LOGGER.debug("%s: checking latest statistics", self.scups)

        statistic_ids = await get_db_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        statistic_ids = [
            x["statistic_id"]
            for x in statistic_ids
            if x["statistic_id"].startswith(self._stat_id_preamble)
        ]

        # fetch last stats
        if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
            last_stats = {
                _stat: await get_db_instance(self.hass).async_add_executor_job(
                    get_last_statistics, self.hass, 1, _stat, True
                )
                for _stat in statistic_ids
            }
        else:
            last_stats = {
                _stat: await get_db_instance(self.hass).async_add_executor_job(
                    get_last_statistics,
                    self.hass,
                    1,
                    _stat,
                    True,
                    {"max", "sum"},
                )
                for _stat in statistic_ids
            }

        # get last record local datetime and eval if any stat is missing
        last_record_dt = {}
        for x in statistic_ids:
            try:
                if MAJOR_VERSION <= 2022:
                    last_record_dt[x] = dt_util.parse_datetime(
                        last_stats[x][x][0]["end"]
                    )
                elif MAJOR_VERSION == 2023 and MINOR_VERSION < 3:
                    last_record_dt[x] = dt_util.as_local(last_stats[x][x][0]["end"])
                else:
                    last_record_dt[x] = dt_util.utc_from_timestamp(
                        last_stats[x][x][0]["end"]
                    )
            except Exception:
                last_record_dt[x] = dt_util.as_utc(datetime(1970, 1, 1))

        # store most recent stat for each statistic_id
        self._last_stats_dt = last_record_dt
        self._last_stats_sum = {
            x: last_stats[x][x][0]["sum"]
            for x in last_stats
            if x in last_stats[x] and "sum" in last_stats[x][x][0]
        }

    async def check_statistics_integrity(self) -> bool:
        """Check if statistics differ from stored data since a given datetime."""

        _LOGGER.warning("Running statistics integrity check")
        self._corrupt_stats = []

        # recalculate all data
        await asyncio.to_thread(self._edata.process_data, False)

        # give from_dt a proper default value
        from_dt = dt_util.as_utc(
            self._edata.data["consumptions_daily_sum"][0]["datetime"]
        )

        _LOGGER.debug(
            "%s: performing integrity check since %s",
            self.scups,
            dt_util.as_local(from_dt),
        )
        # get all statistic_ids starting with edata:<id/scups>
        all_ids = await get_db_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        to_check = [
            x["statistic_id"]
            for x in all_ids
            if x["statistic_id"].startswith(self._stat_id_preamble)
        ]

        if len(to_check) == 0:
            _LOGGER.warning(
                "%s: no statistics found",
                self.scups,
            )
            return False

        data = await get_db_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            from_dt,
            dt_util.as_utc(datetime.now()),
            set(to_check),
            "hour",
            None,
            {"change", "state"},
        )

        # Checksums
        _consumptions_checksum = 0
        _consumptions_tariff_checksum = [0, 0, 0]
        _surplus_checksum = 0

        for c in self._edata.data["consumptions_daily_sum"]:
            _consumptions_checksum += c["value_kWh"]
            _consumptions_tariff_checksum[0] += c["value_p1_kWh"]
            _consumptions_tariff_checksum[1] += c["value_p2_kWh"]
            _consumptions_tariff_checksum[2] += c["value_p3_kWh"]
            _surplus_checksum += c["surplus_kWh"]

        for test_tuple in (
            (_consumptions_checksum, const.STAT_ID_KWH(self.id)),
            (_consumptions_tariff_checksum[0], const.STAT_ID_P1_KWH(self.id)),
            (_consumptions_tariff_checksum[1], const.STAT_ID_P2_KWH(self.id)),
            (_consumptions_tariff_checksum[2], const.STAT_ID_P3_KWH(self.id)),
            (_surplus_checksum, const.STAT_ID_SURP_KWH(self.id)),
        ):
            _stats_sum = 0
            if (stats := data.get(test_tuple[1], None)) is not None:
                _LOGGER.debug(
                    "First evaluated sample of %s is %s",
                    test_tuple[1],
                    dt_util.as_local(dt_util.utc_from_timestamp(stats[0]["start"])),
                )
                for c in stats:
                    _stats_sum += c["change"]
                    if c["change"] < 0:
                        _LOGGER.warning(
                            "%s: negative change found at '%s'",
                            self.scups,
                            test_tuple[1],
                        )
            else:
                _LOGGER.warning(
                    "%s: '%s' statistic not found", self.scups, test_tuple[1]
                )

            if not math.isclose(test_tuple[0], _stats_sum, abs_tol=1):  # +-1kWh
                _LOGGER.warning(
                    "%s: '%s' statistic is corrupt, its checksum is %s, got %s",
                    self.scups,
                    test_tuple[1],
                    test_tuple[0],
                    _stats_sum,
                )
                self._corrupt_stats.append(test_tuple[1])

        _LOGGER.warning(
            "%s: %s corrupt statistics", self.scups, len(self._corrupt_stats)
        )
        return len(self._corrupt_stats) == 0

    async def rebuild_statistics(
        self, from_dt: datetime | None = None, include_only: list[str] | None = None
    ):
        """Rebuild edata statistics since a given datetime. Defaults to last year."""

        _LOGGER.debug("%s: rebuilding statistics", self.scups)

        # recalculate all data
        await asyncio.to_thread(self._edata.process_data, False)

        # get all statistic_ids starting with edata:<id/scups>
        all_ids = await get_db_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        to_clear = [
            x["statistic_id"]
            for x in all_ids
            if x["statistic_id"].startswith(self._stat_id_preamble)
        ]

        # give from_dt a proper default value
        if from_dt is None:
            from_dt = dt_util.as_utc(
                self._edata.data["consumptions_monthly_sum"][0]["datetime"]
            )
            # if from_dt is none, only corrupt stats get a reset
            to_clear = [x for x in to_clear if x in self._corrupt_stats]

        if len(to_clear) == 0:
            _LOGGER.warning("%s: there are no corrupt statistics", to_clear)
            return

        if include_only is not None:
            to_clear = [x for x in include_only if x in to_clear]

        # retrieve stored statistics along with its metadata
        old_metadata = await get_db_instance(self.hass).async_add_executor_job(
            get_metadata, self.hass
        )

        old_data = await get_db_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            dt_util.as_utc(datetime(1970, 1, 1)),
            from_dt,
            set(to_clear),
            "hour",
            None,
            {"state", "sum", "mean", "max"},
        )

        # wipe all-time statistics (since it is the only method provided by home assistant)
        _LOGGER.warning(
            "Clearing statistics for %s",
            to_clear,
        )
        get_db_instance(self.hass).async_clear_statistics(to_clear)

        # now restore old statistics
        for stat_id in old_data:
            if stat_id not in to_clear:
                continue

            self._last_stats_dt[stat_id] = dt_util.utc_from_timestamp(
                old_data[stat_id][-1]["start"]
            )
            self._last_stats_sum[stat_id] = old_data[stat_id][-1]["sum"]

            _LOGGER.warning("Restoring statistic id '%s'", stat_id)
            get_db_instance(self.hass).async_import_statistics(
                old_metadata[stat_id][1],
                [
                    StatisticData(
                        start=dt_util.utc_from_timestamp(x["start"]),
                        state=x["state"],
                        sum=x.get("sum", None),
                        mean=x.get("mean", None),
                        max=x.get("max", None),
                    )
                    for x in old_data[stat_id]
                ],
                Statistics,
            )

        self._corrupt_stats = []

        await self._update_consumption_stats()
        await self._update_maximeter_stats()
        if self.billing_rules:
            # costs are only processed if billing functionality is enabled
            await self._update_cost_stats()

    async def update_statistics(self):
        """Update Long Term Statistics with newly found data."""

        _LOGGER.debug("%s: synchronizing statistics", self.scups)

        # first fetch from db last statistics for current id
        await self._update_last_stats_summary()

        for stat_id in self._last_stats_dt:
            _LOGGER.debug(
                "%s: '%s' most recent data is at %s",
                self.scups,
                stat_id,
                self._last_stats_dt[stat_id],
            )

        await self._update_consumption_stats()
        await self._update_maximeter_stats()

        if self.billing_rules:
            # costs are only processed if billing functionality is enabled
            await self._update_cost_stats()

    async def _add_statistics(self, new_stats):
        """Add new statistics as a bundle."""

        inserted = {
            stat_id: len(values)
            for stat_id, values in new_stats.items()
            if len(values) > 0
        }

        if _LOGGER.isEnabledFor(logging.INFO):
            if inserted:
                compact = ", ".join(
                    f"{stat_id}={inserted[stat_id]}" for stat_id in sorted(inserted)
                )
                _LOGGER.info("%s: statistics batch %s", self.scups, compact)
            else:
                _LOGGER.info("%s: statistics batch has no new values", self.scups)

        for stat_id in new_stats:
            if len(new_stats[stat_id]) > 0:
                _LOGGER.debug(
                    "%s: inserting %s new values for statistic '%s'",
                    self.scups,
                    len(new_stats[stat_id]),
                    stat_id,
                )
            else:
                continue

            if stat_id in self.energy_stat_ids:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_KWH(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                )
            elif stat_id in self.cost_stat_ids:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_EUR(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=CURRENCY_EURO,
                )
            elif stat_id in self.maximeter_stat_ids:
                metadata = StatisticMetaData(
                    has_mean=True,
                    has_sum=False,
                    name=const.STAT_TITLE_KW(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=UnitOfPower.KILO_WATT,
                )
            else:
                continue
            async_add_external_statistics(self.hass, metadata, new_stats[stat_id])

    async def _update_consumption_stats(self) -> dict[str, list[StatisticData]]:
        """Build long-term statistics for consumptions."""

        new_stats = {x: [] for x in self.energy_stat_ids}

        # init as 0 if need
        for stat_id in self.energy_stat_ids:
            if stat_id not in self._last_stats_sum:
                self._last_stats_sum[stat_id] = 0

        _label = "value_kWh"
        for data in self._edata.data.get("consumptions", []):
            dt_found = dt_util.as_local(data["datetime"])
            _p = utils.get_pvpc_tariff(data["datetime"])
            by_tariff_ids = [
                const.STAT_ID_KWH(self.id),
                const.STAT_ID_SURP_KWH(self.id),
            ]
            by_tariff_ids.extend([x for x in self.energy_stat_ids if _p in x])
            for stat_id in by_tariff_ids:
                if (stat_id not in self._last_stats_dt) or (
                    dt_found >= self._last_stats_dt[stat_id]
                ):
                    _label = "value_kWh" if "surp" not in stat_id else "surplus_kWh"
                    if _label in data and data[_label] is not None:
                        new_stats[stat_id].append(
                            StatisticData(
                                start=dt_found,
                                state=data[_label],
                            )
                        )

        for stat_id in new_stats:
            for stat_data in new_stats[stat_id]:
                self._last_stats_sum[stat_id] += stat_data["state"]
                stat_data["sum"] = self._last_stats_sum[stat_id]

        await self._add_statistics(new_stats)

    async def _update_cost_stats(self) -> dict[str, list[StatisticData]]:
        """Build long-term statistics for cost."""

        new_stats = {x: [] for x in self.cost_stat_ids}

        # init as 0 if need
        for stat_id in self.cost_stat_ids:
            if stat_id not in self._last_stats_sum:
                self._last_stats_sum[stat_id] = 0

        _costs_data = self._edata.data.get("cost_hourly_sum", [])
        if len(_costs_data) == 0:
            # return empty stats since billing is apparently not enabled
            return

        for data in _costs_data:
            dt_found = dt_util.as_local(data["datetime"])
            tariff = utils.get_pvpc_tariff(data["datetime"])

            if (const.STAT_ID_POWER_EUR(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_POWER_EUR(self.id)]
            ):
                new_stats[const.STAT_ID_POWER_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["power_term"],
                    )
                )

            if (const.STAT_ID_ENERGY_EUR(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_ENERGY_EUR(self.id)]
            ):
                new_stats[const.STAT_ID_ENERGY_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                    )
                )

            if (const.STAT_ID_EUR(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_EUR(self.id)]
            ):
                new_stats[const.STAT_ID_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
                    )
                )
                
            if (const.STAT_ID_SURPLUS_EUR(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_SURPLUS_EUR(self.id)]
            ):
                new_stats[const.STAT_ID_SURPLUS_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["surplus_term"],
                    )
                )

            if tariff == "p1":
                stat_id_energy_eur_px = const.STAT_ID_P1_ENERGY_EUR(self.id)
                stat_id_eur_px = const.STAT_ID_P1_EUR(self.id)
            elif tariff == "p2":
                stat_id_energy_eur_px = const.STAT_ID_P2_ENERGY_EUR(self.id)
                stat_id_eur_px = const.STAT_ID_P2_EUR(self.id)
            elif tariff == "p3":
                stat_id_energy_eur_px = const.STAT_ID_P3_ENERGY_EUR(self.id)
                stat_id_eur_px = const.STAT_ID_P3_EUR(self.id)

            if (stat_id_energy_eur_px not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[stat_id_energy_eur_px]
            ):
                new_stats[stat_id_energy_eur_px].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                    )
                )

            if (stat_id_eur_px not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[stat_id_eur_px]
            ):
                new_stats[stat_id_eur_px].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
                    )
                )

        for stat_id in new_stats:
            for stat_data in new_stats[stat_id]:
                self._last_stats_sum[stat_id] += stat_data["state"]
                stat_data["sum"] = self._last_stats_sum[stat_id]

        await self._add_statistics(new_stats)

    async def _update_maximeter_stats(self) -> dict[str, list[StatisticData]]:
        """Build long-term statistics for maximeter."""

        _label = "value_kW"
        new_stats = {x: [] for x in self.maximeter_stat_ids}

        for data in self._edata.data.get("maximeter", {}):
            dt_found = dt_util.as_local(data["datetime"])
            stat_id_by_tariff = (
                const.STAT_ID_P1_KW(self.id)
                if utils.get_pvpc_tariff(data["datetime"]) == "p1"
                else const.STAT_ID_P2_KW(self.id)
            )

            if (const.STAT_ID_KW(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_KW(self.id)]
            ):
                new_stats[const.STAT_ID_KW(self.id)].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        max=data[_label],
                    )
                )

            if (stat_id_by_tariff not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[stat_id_by_tariff]
            ):
                new_stats[stat_id_by_tariff].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        max=data[_label],
                    )
                )

        await self._add_statistics(new_stats)

    def soft_wipe(self):
        """Apply a soft wipe."""

        edata_dir = os.path.join(self.hass.config.path(STORAGE_DIR), EDATA_PROG_NAME)
        edata_file = os.path.join(edata_dir, f"edata_{self.cups.lower()}.json")
        edata_backup_file = edata_file + ".bck"

        _LOGGER.warning("%s, soft wipe requested, preparing a backup", self.scups)
        if os.path.exists(edata_file):
            _LOGGER.warning(
                "%s: backup file is '%s', rename it back to '%s' to restore it",
                self.scups,
                edata_backup_file,
                edata_file,
            )
            os.rename(edata_file, edata_backup_file)

        _LOGGER.debug("%s: deleting mem cache", self.scups)
        self._edata.reset()

    async def async_soft_reset(self):
        """Apply an async full reset."""

        await self.hass.async_add_executor_job(self.soft_wipe)
        await self._async_update_data(update_statistics=True)
        if not await self.check_statistics_integrity():
            await self.rebuild_statistics()
        else:
            _LOGGER.warning("%s: statistics recreation is not needed", self.scups)

    def _get_cached_period_start(self) -> datetime:
        """Return the first datetime of the currently cached period."""

        return datetime.today().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) - relativedelta(months=self.cache_months)

    async def _notify_force_reimport_warning(self, scope: str, date_from: datetime) -> None:
        """Create a UI warning when users trigger a forced reimport."""

        persistent_notification.async_create(
            self.hass,
            (
                "Se ha lanzado una recarga forzada de datos de edata. "
                "Esta acción ignora limitaciones temporales de caché y forzará "
                "nueva descarga desde Datadis para el periodo indicado. "
                f"Ámbito: {scope}. Desde: {date_from.isoformat()}."
            ),
            title="edata: recarga forzada en ejecución",
            notification_id=f"edata_force_reimport_{self.id}",
        )

    def _force_clear_datadis_cache(self) -> None:
        """Clear Datadis connector disk cache to bypass 24h request cache."""

        cache_dir = getattr(getattr(self._edata, "datadis_api", None), "_recent_cache_dir", None)
        if cache_dir and os.path.isdir(cache_dir):
            _LOGGER.warning(
                "%s: clearing datadis connector disk cache at %s",
                self.scups,
                cache_dir,
            )
            for cache_file in glob.glob(os.path.join(cache_dir, "*")):
                with contextlib.suppress(OSError):
                    os.remove(cache_file)

    def _force_reset_fetch_rate_limits(self) -> None:
        """Reset helper fetch timestamps to force Datadis calls on button actions."""

        if isinstance(self._edata.last_update, dict):
            for key in self._edata.last_update:
                self._edata.last_update[key] = datetime(1970, 1, 1)

    def _get_force_snapshot_file(self) -> str:
        """Return the file path used to persist forced reimport period snapshots."""

        edata_dir = os.path.join(self.hass.config.path(STORAGE_DIR), EDATA_PROG_NAME)
        os.makedirs(edata_dir, exist_ok=True)
        return os.path.join(edata_dir, f"edata_force_reimport_{self.cups.lower()}.json")

    def _save_force_period_snapshot(self, date_from: datetime) -> None:
        """Persist reimported period data to avoid repeated Datadis calls."""

        keys_to_store = [
            "consumptions",
            "maximeter",
            "consumptions_daily_sum",
            "consumptions_monthly_sum",
            "cost_hourly_sum",
            "cost_daily_sum",
            "cost_monthly_sum",
        ]

        payload: dict = {
            "version": 1,
            "date_from": date_from.isoformat(),
            "cache_months": self.cache_months,
            "created_at": datetime.now().isoformat(),
            "data": {},
        }

        for key in keys_to_store:
            values = self._edata.data.get(key, [])
            if not isinstance(values, list):
                payload["data"][key] = []
                continue

            serialized = []
            for item in values:
                dt_value = item.get("datetime")
                if dt_value is None or dt_value < date_from:
                    continue
                row = dict(item)
                row["datetime"] = dt_value.isoformat()
                serialized.append(row)
            payload["data"][key] = serialized

        snapshot_file = self._get_force_snapshot_file()
        with open(snapshot_file, "w", encoding="utf8") as fdesc:
            json.dump(payload, fdesc)

        payload_rows = len(payload["data"].get("consumptions", []))
        _LOGGER.warning(
            "%s: stored local force-reimport snapshot at %s (consumptions=%s)",
            self.scups,
            snapshot_file,
            payload_rows,
        )

    def _load_force_period_snapshot(self, date_from: datetime) -> bool:
        """Load previously saved period data snapshot if compatible."""

        snapshot_file = self._get_force_snapshot_file()
        if not os.path.exists(snapshot_file):
            _LOGGER.warning("%s: no local force snapshot found", self.scups)
            return False

        try:
            with open(snapshot_file, encoding="utf8") as fdesc:
                payload = json.load(fdesc)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("%s: failed to read force snapshot: %s", self.scups, err)
            return False

        expected_from = date_from.isoformat()
        if payload.get("date_from") != expected_from:
            _LOGGER.warning(
                "%s: force snapshot ignored due date mismatch snapshot=%s expected=%s",
                self.scups,
                payload.get("date_from"),
                expected_from,
            )
            return False
        if payload.get("cache_months") != self.cache_months:
            _LOGGER.warning(
                "%s: force snapshot ignored due cache mismatch snapshot=%s expected=%s",
                self.scups,
                payload.get("cache_months"),
                self.cache_months,
            )
            return False

        keys_to_restore = [
            "consumptions",
            "maximeter",
            "consumptions_daily_sum",
            "consumptions_monthly_sum",
            "cost_hourly_sum",
            "cost_daily_sum",
            "cost_monthly_sum",
        ]

        for key in keys_to_restore:
            previous = self._edata.data.get(key, [])
            keep_older = []
            if isinstance(previous, list):
                keep_older = [
                    item
                    for item in previous
                    if item.get("datetime") is not None and item["datetime"] < date_from
                ]

            restored = []
            for item in payload.get("data", {}).get(key, []):
                row = dict(item)
                dt_raw = row.get("datetime")
                if dt_raw is None:
                    continue
                row["datetime"] = datetime.fromisoformat(dt_raw)
                restored.append(row)

            self._edata.data[key] = keep_older + restored

        _LOGGER.warning(
            "%s: using local force-reimport snapshot from %s (no Datadis call, consumptions=%s)",
            self.scups,
            snapshot_file,
            len(self._edata.data.get("consumptions", [])),
        )
        return True

    def _purge_cached_period_data(self, date_from: datetime) -> None:
        """Delete in-memory period data so fresh payload can overwrite it."""

        keys_to_filter = [
            "consumptions",
            "maximeter",
            "consumptions_daily_sum",
            "consumptions_monthly_sum",
            "cost_hourly_sum",
            "cost_daily_sum",
            "cost_monthly_sum",
        ]
        for key in keys_to_filter:
            values = self._edata.data.get(key, [])
            if isinstance(values, list):
                before = len(values)
                self._edata.data[key] = [
                    item
                    for item in values
                    if item.get("datetime") is not None and item["datetime"] < date_from
                ]
                after = len(self._edata.data[key])
                _LOGGER.warning(
                    "%s: purged key=%s removed=%s kept=%s",
                    self.scups,
                    key,
                    before - after,
                    after,
                )

    def _clear_stats_tracking(self, stat_ids: set[str]) -> None:
        """Reset internal last-stats trackers for selected statistic ids."""

        if self._last_stats_dt is None:
            self._last_stats_dt = {}
        if self._last_stats_sum is None:
            self._last_stats_sum = {}
        for stat_id in stat_ids:
            self._last_stats_dt.pop(stat_id, None)
            self._last_stats_sum.pop(stat_id, None)

    async def _async_force_reimport_period(
        self, date_from: datetime, scope: str = "period"
    ) -> None:
        """Force reimport all metrics for the selected period and overwrite stats."""

        _LOGGER.warning(
            "%s: force reimport start scope=%s date_from=%s",
            self.scups,
            scope,
            date_from.isoformat(),
        )
        await self._notify_force_reimport_warning(scope, date_from)

        def _prepare() -> bool:
            if self._load_force_period_snapshot(date_from):
                return True
            self._purge_cached_period_data(date_from)
            self._force_reset_fetch_rate_limits()
            self._force_clear_datadis_cache()
            return False

        used_local_snapshot = await self.hass.async_add_executor_job(_prepare)
        _LOGGER.warning(
            "%s: force reimport using_snapshot=%s",
            self.scups,
            used_local_snapshot,
        )

        if not used_local_snapshot:
            # The helper fetches one endpoint per update() call (supplies, contracts,
            # consumptions, maximeter, pvpc). Loop until consumptions is fetched or
            # reaching a safety cap.
            _MAX_UPDATE_ITERATIONS = 6
            for _attempt in range(_MAX_UPDATE_ITERATIONS):
                await self._async_update_data(update_statistics=False)
                new_rows = len(self._edata.data.get("consumptions", []))
                _LOGGER.warning(
                    "%s: force reimport update attempt=%d consumptions=%d",
                    self.scups,
                    _attempt + 1,
                    new_rows,
                )
                if new_rows > 0:
                    break

            new_rows = len(self._edata.data.get("consumptions", []))
            if new_rows > 0:
                await self.hass.async_add_executor_job(
                    self._save_force_period_snapshot, date_from
                )
            else:
                _LOGGER.warning(
                    "%s: force reimport fetched zero consumptions after %d attempts, snapshot not saved",
                    self.scups,
                    _MAX_UPDATE_ITERATIONS,
                )

        await asyncio.to_thread(self._edata.process_data, False)
        _LOGGER.warning(
            "%s: force reimport post-process consumptions=%s costs=%s maximeter=%s",
            self.scups,
            len(self._edata.data.get("consumptions", [])),
            len(self._edata.data.get("cost_hourly_sum", [])),
            len(self._edata.data.get("maximeter", [])),
        )

        force_stat_ids = set(self.energy_stat_ids).union(self.maximeter_stat_ids)
        if self.billing_rules:
            force_stat_ids.update(self.cost_stat_ids)

        self._clear_stats_tracking(force_stat_ids)
        _LOGGER.warning(
            "%s: force reimport rebuilding stat_ids=%s from=%s",
            self.scups,
            len(force_stat_ids),
            date_from.isoformat(),
        )

        await self.rebuild_statistics(
            from_dt=dt_util.as_utc(date_from),
            include_only=sorted(force_stat_ids),
        )

        _LOGGER.warning("%s: force reimport finished", self.scups)

    async def async_force_surplus_reimport(self):
        """Force reimport all values for current cache window and overwrite stats."""

        reimport_from = self._get_cached_period_start()
        _LOGGER.warning(
            "%s: force period reimport requested (from %s)",
            self.scups,
            reimport_from.isoformat(),
        )
        await self._async_force_reimport_period(reimport_from)

    async def async_full_import(self):
        """Apply an async full fetch."""

        now = dt_util.now()
        self._full_import_calls += 1

        if self._full_import_last_run is None:
            _LOGGER.warning(
                "%s: import_all_data pressed for the first time", self.scups
            )
        else:
            elapsed = now - self._full_import_last_run
            _LOGGER.warning(
                "%s: import_all_data pressed %d times (elapsed since previous run: %s)",
                self.scups,
                self._full_import_calls,
                elapsed,
            )

        self._full_import_last_run = now

        _LOGGER.warning("Importing last two years of data from Datadis")
        self.set_long_cache()
        await self._async_force_reimport_period(
            self._get_cached_period_start(), scope="full_import"
        )

        self.set_short_cache()
        _LOGGER.debug(
            "%s: reducing cache items to last %s months", self.scups, self.cache_months
        )
        await self._async_update_data(update_statistics=False)

    def set_long_cache(self):
        """Set the number of cached monts to a long value (two years)."""

        self.cache_months = const.CACHE_MONTHS_LONG

    def set_short_cache(self):
        """Set the number of cached monts to a short value (a year)."""

        self.cache_months = const.CACHE_MONTHS_SHORT

    async def update_billing(self, options: dict, since: datetime | None = None):
        """Update billing rules and recalculate."""

        _LOGGER.info("%s: updating costs since %s", self.scups, since.isoformat())
        billing_enabled = options.get(const.CONF_BILLING, False)

        if billing_enabled:
            pricing_rules = {
                const.PRICE_ELECTRICITY_TAX: const.DEFAULT_PRICE_ELECTRICITY_TAX,
                const.PRICE_IVA_TAX: const.DEFAULT_PRICE_IVA,
            }
            pricing_rules.update(
                {
                    x: options[x]
                    for x in options
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
        else:
            pricing_rules = None

        self._edata.pricing_rules = pricing_rules
        self._edata.is_pvpc = options[const.CONF_PVPC]
        self._edata.enable_billing = options[const.CONF_BILLING]

        for key in self._edata.data:
            if not key.startswith("cost"):
                continue
            if since is not None:
                self._edata.data[key] = [
                    x
                    for x in self._edata.data[key]
                    if dt_util.as_local(x["datetime"]) < since
                ]
            else:
                self._edata.data[key] = []

        await asyncio.to_thread(self._edata.process_cost)

        await self.rebuild_statistics(since, self.cost_stat_ids)
