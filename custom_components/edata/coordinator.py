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
import shutil

from dateutil.relativedelta import relativedelta

from edata.const import PROG_NAME as EDATA_PROG_NAME
from edata.definitions import ATTRIBUTES, PricingRules
from edata.helpers import EdataHelper
from edata.storage import dump_storage as edata_dump_storage
from edata.processors import utils
from homeassistant.components import persistent_notification
from homeassistant.components.recorder.db_schema import Statistics
from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
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

# Extra keys injected in-memory by _enrich_consumptions_from_cache / _apply_extras_sidecar.
# They must NOT be present when passing consumptions to the edata library, which uses
# EdataSchema (voluptuous PREVENT_EXTRA) internally in BillingProcessor and dump_storage.
_EXTRAS_KEYS: frozenset[str] = frozenset(
    {"generation_kWh", "self_consumption_kWh", "obtain_method"}
)


@contextlib.contextmanager
def _clean_consumptions(consumptions: list[dict]):
    """Context manager that temporarily strips extra keys from consumption records.

    Pops _EXTRAS_KEYS from each record on enter, restores the saved values on exit.
    This lets callers pass the raw in-memory list to edata library functions that
    validate with EdataSchema (PREVENT_EXTRA) without copying the whole list.
    """
    saved: list[dict] = []
    for rec in consumptions:
        snapshot = {k: rec.pop(k) for k in _EXTRAS_KEYS if k in rec}
        saved.append(snapshot)
    try:
        yield
    finally:
        for rec, snapshot in zip(consumptions, saved):
            rec.update(snapshot)


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

        self.solar_stat_ids = {
            const.STAT_ID_GENERATION(self.id),
            const.STAT_ID_SELF_CONSUMPTION(self.id),
        }

        self.energy_stat_ids = self.consumptions_stat_ids.union(self.surplus_stat_ids).union(self.solar_stat_ids)

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
            self.scups,
            bool(self.authorized_nif),
            self.billing_rules is not None,
        )

        # Run the update in a worker and wait for completion before continuing.
        # e-data's async wrapper can return before the underlying update is done.
        # _must_dump=False: we handle the dump ourselves after enrichment.
        self._edata._must_dump = False
        try:
            update_result = await asyncio.to_thread(
                self._edata.update,
                date_from,
                date_to,
            )
        finally:
            self._edata._must_dump = True
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
            _supply_cups = self._edata.data["supplies"][0].get("cups", "")
            _LOGGER.warning(
                "%s: update supplies sample cups=...%s date_start=%s date_end=%s",
                self.scups,
                _supply_cups[-4:] if _supply_cups else "?",
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

        if post_counts["consumptions"] > 0:
            # 1. Dump clean data first — edata's EdataSchema (voluptuous) uses
            #    PREVENT_EXTRA so any unknown keys raise Invalid. Strip extras
            #    temporarily via context manager and restore them afterwards.
            _consumptions = self._edata.data.get("consumptions", [])
            with _clean_consumptions(_consumptions):
                await self.hass.async_add_executor_job(
                    edata_dump_storage,
                    self._edata._cups,
                    self._edata.data,
                    self._edata._storage_dir,
                )
            # 2. Enrich in-memory consumptions with fields the library drops
            #    (generation_kWh, self_consumption_kWh, obtain_method) and
            #    persist them to a sidecar JSON file we own.
            await self.hass.async_add_executor_job(self._enrich_consumptions_from_cache)
            # 3. Apply all previously saved extras (including months whose
            #    disk-cache files have already expired).
            await self.hass.async_add_executor_job(self._apply_extras_sidecar)
            await self.hass.async_add_executor_job(self._rotate_storage_backup)
        else:
            _LOGGER.warning(
                "%s: skipping dump — consumptions still zero after update",
                self.scups,
            )

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
                _consumptions = self._edata.data.get("consumptions", [])
                with _clean_consumptions(_consumptions):
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
            monthly = list(self._edata.data["consumptions_monthly_sum"])
            monthly = await self.hass.async_add_executor_job(
                self._enrich_monthly_with_sidecar, monthly
            )
            self._data[const.WS_CONSUMPTIONS_MONTH] = monthly
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
        _consumptions = self._edata.data.get("consumptions", [])
        with _clean_consumptions(_consumptions):
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
        _consumptions = self._edata.data.get("consumptions", [])
        with _clean_consumptions(_consumptions):
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
        await self._update_solar_stats()
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
        await self._update_solar_stats()

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
                    mean_type=StatisticMeanType.NONE,
                    has_sum=True,
                    name=const.STAT_TITLE_KWH(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                    unit_class="energy",
                )
            elif stat_id in self.cost_stat_ids:
                metadata = StatisticMetaData(
                    has_mean=False,
                    mean_type=StatisticMeanType.NONE,
                    has_sum=True,
                    name=const.STAT_TITLE_EUR(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=CURRENCY_EURO,
                )
            elif stat_id in self.maximeter_stat_ids:
                metadata = StatisticMetaData(
                    has_mean=True,
                    mean_type=StatisticMeanType.ARITHMETIC,
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

    def _read_sidecar_sync(self) -> dict:
        """Read the extras sidecar JSON synchronously (safe to run in executor)."""
        sidecar_path = self._get_extras_sidecar_path()
        extras: dict[str, dict] = {}
        with contextlib.suppress(Exception):
            with open(sidecar_path, encoding="utf8") as fh:
                extras = json.load(fh)
        return extras

    async def _update_solar_stats(self) -> None:
        """Build LTS statistics for solar generation and self-consumption from sidecar."""

        new_stats = {x: [] for x in self.solar_stat_ids}

        for stat_id in self.solar_stat_ids:
            if stat_id not in self._last_stats_sum:
                self._last_stats_sum[stat_id] = 0

        extras: dict[str, dict] = await self.hass.async_add_executor_job(
            self._read_sidecar_sync
        )

        if not extras:
            _LOGGER.debug("%s: no solar sidecar data, skipping solar stats", self.scups)
            return

        gen_id = const.STAT_ID_GENERATION(self.id)
        self_id = const.STAT_ID_SELF_CONSUMPTION(self.id)

        for iso_key, fields in sorted(extras.items()):
            try:
                dt_entry = dt_util.as_local(datetime.fromisoformat(iso_key))
            except (ValueError, TypeError):
                continue

            gen_val = fields.get("generation_kWh") or 0.0
            self_val = fields.get("self_consumption_kWh") or 0.0

            if gen_val > 0 and (
                gen_id not in self._last_stats_dt
                or dt_entry >= self._last_stats_dt[gen_id]
            ):
                new_stats[gen_id].append(StatisticData(start=dt_entry, state=gen_val))

            if self_val > 0 and (
                self_id not in self._last_stats_dt
                or dt_entry >= self._last_stats_dt[self_id]
            ):
                new_stats[self_id].append(StatisticData(start=dt_entry, state=self_val))

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

    def _enrich_monthly_with_sidecar(self, monthly: list) -> list:
        """Add generation_kWh, self_consumption_kWh and cost sub-terms to monthly websocket records.

        Each monthly record already has datetime, value_kWh, surplus_kWh, etc.
        We aggregate the sidecar hourly extras by billing-cycle month and attach
        generation_kWh and self_consumption_kWh totals to each record.
        We also join cost_monthly_sum fields (energy_term, power_term, surplus_term,
        others_term, value_eur) so the frontend needs only one websocket call.
        """
        extras: dict[str, dict] = self._read_sidecar_sync()

        # Aggregate sidecar by the same billing-cycle month key used in monthly records.
        # Monthly records have datetime = first day of billing cycle (after cycle_start_day offset).
        # We use the same relativedelta logic as BillingProcessor: shift back cycle_start_day-1 days.
        cycle_offset = 0
        if self.billing_rules and hasattr(self.billing_rules, "__getitem__"):
            with contextlib.suppress(Exception):
                cycle_offset = self.billing_rules["cycle_start_day"] - 1

        agg: dict[str, dict[str, float]] = {}
        for iso_key, fields in extras.items():
            try:
                dt_entry = datetime.fromisoformat(iso_key)
            except (ValueError, TypeError):
                continue
            day = dt_entry.replace(hour=0, minute=0, second=0, microsecond=0)
            month_key = (day - timedelta(days=cycle_offset)).replace(day=1).isoformat()
            if month_key not in agg:
                agg[month_key] = {"generation_kWh": 0.0, "self_consumption_kWh": 0.0}
            agg[month_key]["generation_kWh"] += fields.get("generation_kWh") or 0.0
            agg[month_key]["self_consumption_kWh"] += fields.get("self_consumption_kWh") or 0.0

        # Build cost monthly lookup keyed by month ISO datetime string
        cost_by_month: dict[str, dict] = {}
        for cost_rec in self._edata.data.get("cost_monthly_sum", []):
            rec_dt = cost_rec.get("datetime")
            if rec_dt is None:
                continue
            cost_by_month[rec_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()] = cost_rec

        if not agg and not cost_by_month:
            return monthly

        enriched = []
        for record in monthly:
            rec = dict(record)
            rec_dt = rec.get("datetime")
            if rec_dt is not None:
                month_key = (
                    rec_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    .isoformat()
                )
                if month_key in agg:
                    rec["generation_kWh"] = round(agg[month_key]["generation_kWh"], 3)
                    rec["self_consumption_kWh"] = round(agg[month_key]["self_consumption_kWh"], 3)
                else:
                    rec["generation_kWh"] = 0.0
                    rec["self_consumption_kWh"] = 0.0
                if month_key in cost_by_month:
                    c = cost_by_month[month_key]
                    rec["energy_term"] = round(c.get("energy_term") or 0.0, 4)
                    rec["power_term"] = round(c.get("power_term") or 0.0, 4)
                    rec["surplus_term"] = round(c.get("surplus_term") or 0.0, 4)
                    rec["others_term"] = round(c.get("others_term") or 0.0, 4)
                    rec["value_eur"] = round(c.get("value_eur") or 0.0, 4)
            enriched.append(rec)
        return enriched

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

    # ------------------------------------------------------------------
    # Rolling backup helpers (replaces single-snapshot logic)
    # ------------------------------------------------------------------

    _BACKUP_RETENTION_DAYS = 30

    def _get_backups_dir(self) -> str:
        """Return the path to the rolling backups directory."""

        edata_dir = os.path.join(self.hass.config.path(STORAGE_DIR), EDATA_PROG_NAME)
        backups_dir = os.path.join(edata_dir, "backups")
        os.makedirs(backups_dir, exist_ok=True)
        return backups_dir

    def _get_extras_sidecar_path(self) -> str:
        """Return path to the extras sidecar JSON file.

        edata_CUPS_extras.json lives alongside edata_CUPS.json in the edata
        storage subdir. It is owned entirely by this coordinator and never
        passed through edata's EdataSchema validation.
        """
        edata_dir = os.path.join(self.hass.config.path(STORAGE_DIR), EDATA_PROG_NAME)
        return os.path.join(
            edata_dir, f"edata_{self._edata._cups.lower()}_extras.json"
        )

    def _enrich_consumptions_from_cache(self) -> int:
        """Read fresh Datadis disk-cache files and persist extra fields.

        Extracts generation_kWh, self_consumption_kWh and obtain_method from
        the connector's cache, saves them to a sidecar JSON file (accumulative,
        keyed by ISO datetime string) and applies them to in-memory consumptions.

        Note: These fields cannot be saved inside edata_CUPS.json because the
        library's EdataSchema (voluptuous PREVENT_EXTRA) rejects unknown keys.
        The sidecar file edata_CUPS_extras.json is owned by this coordinator.

        Returns the number of in-memory entries enriched in this call.
        """
        cache_dir = os.path.join(
            self.hass.config.path(STORAGE_DIR), EDATA_PROG_NAME, "cache"
        )
        if not os.path.isdir(cache_dir):
            _LOGGER.debug("%s: cache dir not found, skipping enrichment", self.scups)
            return 0

        # Build lookup from fresh cache: datetime object → extra fields
        extra: dict[datetime, dict] = {}
        for cache_file in glob.glob(os.path.join(cache_dir, "*")):
            try:
                with open(cache_file, encoding="utf8") as fh:
                    items = json.load(fh)
                if not isinstance(items, list) or not items:
                    continue
                # Only process consumption responses (keyed by consumptionKWh)
                if "consumptionKWh" not in items[0]:
                    continue
                for item in items:
                    if not all(k in item for k in ("date", "time", "consumptionKWh")):
                        continue
                    try:
                        hour = str(int(item["time"].split(":")[0]) - 1)
                        dt_key = datetime.strptime(
                            f"{item['date']} {hour.zfill(2)}:00", "%Y/%m/%d %H:%M"
                        )
                    except (ValueError, IndexError):
                        continue
                    generation = item.get("generationEnergyKWh")
                    self_cons = item.get("selfConsumptionEnergyKWh")
                    obtain = item.get("obtainMethod")
                    if any(v is not None for v in (generation, self_cons, obtain)):
                        extra[dt_key] = {
                            "generation_kWh": generation,
                            "self_consumption_kWh": self_cons,
                            "obtain_method": obtain,
                        }
            except (json.JSONDecodeError, OSError, KeyError):
                continue

        if not extra:
            _LOGGER.debug("%s: no extra fields found in cache", self.scups)
            return 0

        # Merge new extras into sidecar (accumulative across update cycles)
        sidecar_path = self._get_extras_sidecar_path()
        existing_extras: dict[str, dict] = {}
        with contextlib.suppress(Exception):
            with open(sidecar_path, encoding="utf8") as fh:
                existing_extras = json.load(fh)
        for dt_key, fields in extra.items():
            existing_extras[dt_key.isoformat()] = fields
        with contextlib.suppress(Exception):
            os.makedirs(os.path.dirname(sidecar_path), exist_ok=True)
            with open(sidecar_path, "w", encoding="utf8") as fh:
                json.dump(existing_extras, fh)

        # Apply to in-memory consumptions (matching by datetime object)
        enriched = 0
        for entry in self._edata.data.get("consumptions", []):
            entry_dt = entry.get("datetime")
            if entry_dt in extra:
                entry.update(extra[entry_dt])
                enriched += 1

        _LOGGER.debug(
            "%s: enriched %d/%d entries from cache; sidecar now %d entries",
            self.scups,
            enriched,
            len(self._edata.data.get("consumptions", [])),
            len(existing_extras),
        )
        return enriched

    def _apply_extras_sidecar(self) -> int:
        """Apply all saved extras from the sidecar file to in-memory consumptions.

        Called after every successful update to restore extra Datadis fields
        for entries whose disk-cache files have already expired (> 24 h old).
        Safe to call repeatedly — entry.update() with the same values is a no-op.

        Returns the number of in-memory entries that received extra fields.
        """
        sidecar_path = self._get_extras_sidecar_path()
        extras: dict[str, dict] = {}
        with contextlib.suppress(Exception):
            with open(sidecar_path, encoding="utf8") as fh:
                extras = json.load(fh)

        if not extras:
            return 0

        enriched = 0
        for entry in self._edata.data.get("consumptions", []):
            entry_dt = entry.get("datetime")
            if entry_dt is None:
                continue
            key = (
                entry_dt.isoformat()
                if hasattr(entry_dt, "isoformat")
                else str(entry_dt)
            )
            if key in extras:
                entry.update(extras[key])
                enriched += 1

        _LOGGER.debug(
            "%s: applied extras to %d/%d entries from sidecar (%d total in sidecar)",
            self.scups,
            enriched,
            len(self._edata.data.get("consumptions", [])),
            len(extras),
        )
        return enriched

    def _rotate_storage_backup(self) -> None:
        """Copy current on-disk storage to dated backup; prune files > 30 days.

        Only runs when the on-disk file has consumptions > 0 so we never
        rotate an empty/broken state into the backup history.
        """

        edata_dir = os.path.join(self.hass.config.path(STORAGE_DIR), EDATA_PROG_NAME)
        src = os.path.join(edata_dir, f"edata_{self.cups.lower()}.json")
        if not os.path.exists(src):
            return

        try:
            with open(src, encoding="utf8") as f:
                data = json.load(f)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("%s: backup rotation skipped, cannot read storage: %s", self.scups, err)
            return

        if len(data.get("consumptions", [])) == 0:
            _LOGGER.warning("%s: backup rotation skipped, storage has no consumptions", self.scups)
            return

        backups_dir = self._get_backups_dir()
        today_str = datetime.today().strftime("%Y-%m-%d")
        dst = os.path.join(backups_dir, f"edata_{self.cups.lower()}_{today_str}.json")

        shutil.copy2(src, dst)
        _LOGGER.warning(
            "%s: storage backup rotated → %s (consumptions=%d)",
            self.scups,
            dst,
            len(data.get("consumptions", [])),
        )

        # Prune backups older than retention limit
        cutoff = datetime.today() - timedelta(days=self._BACKUP_RETENTION_DAYS)
        for bfile in glob.glob(os.path.join(backups_dir, f"edata_{self.cups.lower()}_*.json")):
            bname = os.path.basename(bfile)
            try:
                date_part = bname.replace(f"edata_{self.cups.lower()}_", "").replace(".json", "")
                bdate = datetime.strptime(date_part, "%Y-%m-%d")
                if bdate < cutoff:
                    os.remove(bfile)
                    _LOGGER.warning("%s: pruned old backup %s", self.scups, bname)
            except (ValueError, OSError):
                pass

    def _load_latest_storage_backup(self, date_from: datetime) -> bool:
        """Load the most recent rolling backup that has consumptions into memory.

        Keeps in-memory data before date_from untouched; replaces everything
        from date_from onwards with backup content. Returns True if loaded.
        """

        backups_dir = self._get_backups_dir()
        candidates = sorted(
            glob.glob(os.path.join(backups_dir, f"edata_{self.cups.lower()}_*.json")),
            reverse=True,  # newest first
        )

        selected = None
        selected_cons = 0
        for bfile in candidates:
            try:
                with open(bfile, encoding="utf8") as f:
                    payload = json.load(f)
                n = len(payload.get("consumptions", []))
                if n > 0:
                    selected = (bfile, payload)
                    selected_cons = n
                    break
            except Exception:  # pylint: disable=broad-except
                continue

        if selected is None:
            _LOGGER.warning("%s: no usable storage backup found in %s", self.scups, backups_dir)
            return False

        bfile, payload = selected
        keys = [
            "consumptions",
            "maximeter",
            "consumptions_daily_sum",
            "consumptions_monthly_sum",
            "cost_hourly_sum",
            "cost_daily_sum",
            "cost_monthly_sum",
        ]

        for key in keys:
            # Keep existing in-memory entries that predate date_from
            previous = self._edata.data.get(key, [])
            keep_older = [
                item for item in previous
                if isinstance(item, dict)
                and item.get("datetime") is not None
                and item["datetime"] < date_from
            ]
            # Deserialize backup entries (datetimes are ISO strings in the file)
            restored = []
            for item in payload.get(key, []):
                row = dict(item)
                dt_raw = row.get("datetime")
                if dt_raw is None:
                    continue
                if not isinstance(dt_raw, datetime):
                    try:
                        row["datetime"] = datetime.fromisoformat(str(dt_raw))
                    except (ValueError, TypeError):
                        continue
                restored.append(row)
            self._edata.data[key] = keep_older + restored

        _LOGGER.warning(
            "%s: loaded storage backup %s (consumptions=%d)",
            self.scups,
            os.path.basename(bfile),
            selected_cons,
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
            # Try to load the most recent rolling backup (backups/ dir).
            # This avoids any Datadis call and is safe even after 429 lockouts.
            if self._load_latest_storage_backup(date_from):
                return True
            # No usable backup: purge in-memory period data and reset rate limits
            # so update() will re-fetch from Datadis (or disk-cache if still valid).
            self._purge_cached_period_data(date_from)
            self._force_reset_fetch_rate_limits()
            return False

        used_local_snapshot = await self.hass.async_add_executor_job(_prepare)
        _LOGGER.warning(
            "%s: force reimport using_snapshot=%s",
            self.scups,
            used_local_snapshot,
        )

        if not used_local_snapshot:
            # Log disk-cache state so we know if connector will use cached data
            # or hit Datadis live. Empty files (size=0) are 429 markers.
            _cache_dir = self._edata.datadis_api._recent_cache_dir

            def _log_cache_state():
                if not os.path.isdir(_cache_dir):
                    return
                _cache_files = glob.glob(os.path.join(_cache_dir, "*"))
                _with_data = sum(1 for f in _cache_files if os.path.getsize(f) > 0)
                _LOGGER.warning(
                    "%s: force reimport disk-cache files=%d with_data=%d empty_markers=%d",
                    self.scups,
                    len(_cache_files),
                    _with_data,
                    len(_cache_files) - _with_data,
                )

            await self.hass.async_add_executor_job(_log_cache_state)
            # Prevent update() from calling dump_storage() with empty data.
            # If Datadis returns nothing (429 / throttle), update() would overwrite
            # the on-disk storage file with an empty consumptions list, destroying
            # all previously saved history. We restore _must_dump after the call.
            self._edata._must_dump = False
            try:
                # update() fetches all endpoints (supplies, contracts, consumptions,
                # maximeter) in a single call. With rate limits reset to epoch above,
                # all guards pass and everything is attempted at once.
                await self._async_update_data(update_statistics=False)
            finally:
                self._edata._must_dump = True

            new_rows = len(self._edata.data.get("consumptions", []))
            _LOGGER.warning(
                "%s: force reimport update consumptions=%d",
                self.scups,
                new_rows,
            )
            if new_rows > 0:
                _first_c = self._edata.data["consumptions"][0]
                _last_c = self._edata.data["consumptions"][-1]
                _LOGGER.warning(
                    "%s: force reimport consumptions sample "
                    "first_dt=%s first_surplus=%s last_dt=%s last_surplus=%s",
                    self.scups,
                    _first_c.get("datetime"),
                    _first_c.get("surplus_kWh"),
                    _last_c.get("datetime"),
                    _last_c.get("surplus_kWh"),
                )

            if new_rows == 0:
                _LOGGER.warning(
                    "%s: force reimport fetched zero consumptions — Datadis may be throttling; retry later",
                    self.scups,
                )
            # Rotation is triggered automatically inside _async_update_data
            # when consumptions > 0, so no explicit save needed here.

        # process_data(False) recalculates aggregates and dumps to disk.
        # Only do this when we have actual data; if consumptions is empty
        # we skip the dump to avoid overwriting the on-disk history with zeros.
        _has_data = len(self._edata.data.get("consumptions", [])) > 0
        _consumptions = self._edata.data.get("consumptions", [])
        with _clean_consumptions(_consumptions):
            if _has_data:
                await asyncio.to_thread(self._edata.process_data, False)
            else:
                await asyncio.to_thread(self._edata.process_data, True)
        _LOGGER.warning(
            "%s: force reimport post-process consumptions=%s costs=%s maximeter=%s",
            self.scups,
            len(self._edata.data.get("consumptions", [])),
            len(self._edata.data.get("cost_hourly_sum", [])),
            len(self._edata.data.get("maximeter", [])),
        )

        force_stat_ids = set(self.energy_stat_ids).union(self.maximeter_stat_ids).union(self.solar_stat_ids)
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
        # Prevent update() from dumping empty state if Datadis returns nothing.
        # _async_update_data will trigger _rotate_storage_backup only when
        # consumptions > 0, so the rolling backup is always consistent.
        self._edata._must_dump = False
        try:
            await self._async_update_data(update_statistics=False)
        finally:
            self._edata._must_dump = True

        _consumptions = self._edata.data.get("consumptions", [])
        if len(_consumptions) > 0:
            with _clean_consumptions(_consumptions):
                await asyncio.to_thread(self._edata.process_data)

        # Repair statistics only if they have become corrupt (normal, non-forced path) (normal, non-forced path)
        if not await self.check_statistics_integrity():
            await self.rebuild_statistics()
        else:
            _LOGGER.warning("%s: statistics recreation is not needed", self.scups)

        self.set_short_cache()
        _LOGGER.debug(
            "%s: reducing cache items to last %s months", self.scups, self.cache_months
        )
        self._edata._must_dump = False
        try:
            await self._async_update_data(update_statistics=False)
        finally:
            self._edata._must_dump = True

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

        _consumptions = self._edata.data.get("consumptions", [])
        with _clean_consumptions(_consumptions):
            await asyncio.to_thread(self._edata.process_cost)

        await self.rebuild_statistics(since, self.cost_stat_ids)
