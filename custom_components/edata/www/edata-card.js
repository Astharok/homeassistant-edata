import {
  LitElement,
  html,
} from "https://cdn.jsdelivr.net/npm/lit-element@4.1.1/+esm";
import "https://cdnjs.cloudflare.com/ajax/libs/apexcharts/5.3.3/apexcharts.min.js?module";
import tinycolor from "https://esm.sh/tinycolor2";
// Set program constants and definitions
const PROG_NAME = "edata-card";
const VALID_CHART_TEMPLATES = [
  "consumptions",
  "surplus",
  "maximeter",
  "costs",
  "summary-last-day",
  "summary-last-month",
  "summary-month",
];
const DEF_CHART_TEMPLATE = "";
const VALID_AGGR_PERIODS = ["year", "month", "week", "day", "hour"];
const DEF_AGGR_PERIOD = "month";
const DEF_RECORDS_FOR_METHOD = {
  year: 3,
  month: 13,
  week: 4,
  day: 60,
  hour: 48,
};
const DEF_ROUND_DECIMALS = 1;
const DEF_ENERGY_UNIT = "kWh";
const DEF_POWER_UNIT = "kW";
const DEF_COST_UNIT = "€";
const LABELS_BY_LOCALE = {
  es: {
    p1: "Punta",
    p2: "Llano",
    p3: "Valle",
    p2_3: "Llano y Valle",
    surplus: "Retorno",
    title: "Título",
    entity: "Entidad",
    chart: "Gráfica",
    aggr: "Agregación (no aplica en resúmenes)",
    records: "Registros (no aplica en resúmenes)",
    total: "Total",
    date: "Fecha",
    cost: "Coste",
  },
  ca: {
    p1: "Punta",
    p2: "Pla",
    p3: "Vall",
    p2_3: "Pla i Vall",
    surplus: "Retorn",
    title: "Títol",
    entity: "Entitat",
    chart: "Gràfica",
    aggr: "Agrupació (no aplica en resums)",
    records: "Registres (no aplica en resums)",
    total: "Total",
    date: "Data",
    cost: "Cost",
  },
  gl: {
    p1: "Punta",
    p2: "Chan",
    p3: "Val",
    p2_3: "Chan e Val",
    surplus: "Retorno",
    title: "Título",
    entity: "Entidade",
    chart: "Gráfica",
    aggr: "Agrupación (non aplica en resumos)",
    records: "Rexistros (non aplica en resumos)",
    total: "Total",
    date: "Data",
    cost: "Custo",
  },
  en: {
    p1: "Peak",
    p2: "Flat",
    p3: "Valley",
    p2_3: "Flat and Valley",
    surplus: "Return",
    title: "Title",
    entity: "Entity",
    chart: "Chart",
    aggr: "Aggregation (not applicable in summaries)",
    records: "Records (not applicable in summaries)",
    total: "Total",
    date: "Date",
    cost: "Cost",
  },
};

let locale = navigator.languages
  ? navigator.languages[0]
  : navigator.language || navigator.userLanguage;

function getLabel(key) {
  if (locale in LABELS_BY_LOCALE) return LABELS_BY_LOCALE[locale][key];
  else return LABELS_BY_LOCALE["en"][key];
}

// Set apexcharts defaults:
Apex.xaxis = {
  type: "datetime",
  labels: {
    datetimeUTC: false,
  },
};

Apex.chart = {
  toolbar: {
    show: false,
  },
  zoom: {
    enabled: false,
  },
  animations: {
    enabled: false,
  },
  background: "transparent",
};

Apex.yaxis = {
  labels: {
    formatter: (value) => {
      return value.toFixed(DEF_ROUND_DECIMALS);
    },
  },
};

Apex.dataLabels = {
  enabled: false,
};

Apex.tooltip = {
  enabled: true,
  intersect: false,
  shared: true,
  onDataHover: {
    highlightDataSeries: false,
  },
};

Apex.colors = ["#e54304", "#ff9e22", "#9ccc65"];

// EdataCard class
class EdataCard extends LitElement {
  constructor() {
    super();
    this._loaded = false;
  }

  static get properties() {
    return {
      hass: {},
      config: {},
      _top_left_title: "",
      _top_left_value: "",
      _top_left_unit: "",
      _bottom_left_title: "",
      _bottom_left_value: "",
      _bottom_left_unit: "",
      _top_right_title: "",
      _top_right_value: "",
      _top_right_unit: "",
      _bottom_right_title: "",
      _bottom_right_value: "",
      _bottom_right_unit: "",
    };
  }

  static getConfigElement() {
    // Create and return an editor element
    return document.createElement("edata-card-editor");
  }

  static getStubConfig() {
    return {
      entity: undefined,
      chart: "summary-last-month",
      title: "",
    };
  }

  set hass(hass) {
    this._hass = hass;

    // Override defaults based on dark mode
    let backgroundColor = window.getComputedStyle(document.documentElement).getPropertyValue('--card-background-color');
    const isLightTheme = tinycolor(backgroundColor).getLuminance() > 0.5

    if (hass.themes.darkMode || !isLightTheme) {
      Apex.theme = {
        mode: "dark",
      };
    }

    // Override locale
    locale = hass.locale["language"];
  }

  render() {
    return html`
      <ha-card>
        <div
          style="color: var(--secondary-text-color); font-size: 16px; font-weight: 500; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; padding-left: 15px; padding-top: 15px; "
        >
          ${this._title}
        </div>

        <div
          style="position: relative; width: 100%; height: 100%; margin: 0 auto;"
        >
          <div
            id="left"
            style="position: absolute; width: 40%; height: 90%; top: 0; left: 10px; display: flex; align-items: top; justify-content: left; padding-top: 10px"
          >
            <div
              id="top-left-box"
              style="padding-left: 10px; padding-top: 10px"
            >
              <span style="font-size: 20px; font-weight: bold;"
                >${this._top_left_value}</span
              ><span
                style="font-size: 14px; color: var(--secondary-text-color);"
              >
                ${this._top_left_unit}</span
              >
              <br /><span
                style="color: var(--secondary-text-color); font-size: 14px;"
                >${this._top_left_title}</span
              >
            </div>
            <div
              id="bottom-left-box"
              style="position:absolute; padding-left: 10px; bottom: 10px;"
            >
              <span style="color: var(--secondary-text-color); font-size: 14px;"
                >${this._bottom_left_title}</span
              >
              <br /><span style="font-size: 20px; font-weight: bold;"
                >${this._bottom_left_value}</span
              ><span
                style="font-size: 14px; color: var(--secondary-text-color);"
              >
                ${this._bottom_left_unit}</span
              >
            </div>
          </div>

          <div
            id="right"
            style="position: absolute; width: 40%; height: 90%; top: 0; right: 10px; display: flex; align-items: top; justify-content: right; padding-top: 10px"
          >
            <div
              id="top-right-box"
              style="padding-right: 10px; padding-top: 10px; text-align: right"
            >
              <span style="font-size: 20px; font-weight: bold;"
                >${this._top_right_value}</span
              ><span
                style="font-size: 14px; color: var(--secondary-text-color);"
              >
                ${this._top_right_unit}</span
              >
              <br /><span
                style="color: var(--secondary-text-color); font-size: 14px;"
                >${this._top_right_title}</span
              >
            </div>
            <div
              id="bottom-right-box"
              style="position:absolute; padding-right: 10px; bottom: 10px; text-align: right;"
            >
              <span style="color: var(--secondary-text-color); font-size: 14px;"
                >${this._bottom_right_title}</span
              >
              <br /><span style="font-size: 20px; font-weight: bold;"
                >${this._bottom_right_value}</span
              ><span
                style="font-size: 14px; color: var(--secondary-text-color);"
              >
                ${this._bottom_right_unit}</span
              >
            </div>
          </div>

          <div
            style="position: relative; width: 100%; height: 100%; margin: 0 auto"
          >
            <div
              id="chart"
              style="display: flex; justify-content: center; align-items: center;"
            ></div>
          </div>
        </div>
      </ha-card>
    `;
  }

  setConfig(config) {
    if (!config.entity?.startsWith("sensor.edata")) {
      throw new Error("You need to define a valid entity (sensor.edata_XXXX)");
    }

    // extract scups
    this._scups = config.entity.split("_")[1];

    // config validation
    this._entity = config.entity;
    this._template = VALID_CHART_TEMPLATES.includes(config.chart)
      ? config.chart
      : DEF_CHART_TEMPLATE;
    this._aggr = VALID_AGGR_PERIODS.includes(config.aggr)
      ? config.aggr
      : DEF_AGGR_PERIOD;
    this._records = Number.isInteger(config.records)
      ? config.records
      : DEF_RECORDS_FOR_METHOD[this._aggr];
    this._title = config.title;

    this._colors = config.colors || Apex.colors;

    // store original config
    this._config = config;
  }

  connectedCallback() {
    super.connectedCallback();
    if (!this._loaded) {
      this.renderChart();
    }
  }

  updated(changedProps) {
    super.updated(changedProps);
    if (!this._loaded) {
      this.renderChart();
    }
  }

  async getBarChartOptions(endpoint, unit, tariffs) {
    let results;
    if (tariffs?.length > 0) {
      results = await Promise.all(
        tariffs.map((tariff) =>
          this._hass.callWS({
            type: endpoint,
            scups: this._scups,
            aggr: this._aggr,
            tariff: tariff,
            records: this._records,
          })
        )
      );
    } else {
      results = [
        await this._hass.callWS({
          type: endpoint,
          scups: this._scups,
          aggr: this._aggr,
          records: this._records,
        }),
      ];
    }

    const series = tariffs?.length
      ? tariffs.map((tariff, index) => ({
          name: getLabel(tariff),
          data: this.normalizeX(...results)[index],
        }))
      : [
          {
            name: getLabel("total"),
            data: results[0],
          },
        ];

    var config = {
      chart: {
        stacked: true,
        id: "chart",
        type: "bar",
      },
      colors: this._colors,
      yaxis: {
        title: {
          text: unit,
        },
      },
      series: series,
    };

    if (this._aggr == "year") {
      config["xaxis"] = {
        tickAmount: "dataPoints",
        labels: {
          datetimeUTC: false,
          formatter: function (val) {
            return new Date(val).getFullYear().toString();
          },
        },
      };
    }

    return config;
  }

  async getMaximeterChartOptions() {
    return {
      chart: {
        id: "chart",
        type: "scatter",
      },
      colors: this._colors,
      yaxis: {
        title: {
          text: DEF_POWER_UNIT,
        },
      },
      series: [
        {
          name: getLabel("p1"),
          data: await this._hass.callWS({
            type: "edata/ws/maximeter",
            scups: this._scups,
            tariff: "p1",
          }),
        },
        {
          name: getLabel("p2_3"),
          data: await this._hass.callWS({
            type: "edata/ws/maximeter",
            scups: this._scups,
            tariff: "p2",
          }),
        },
      ],
    };
  }

  async getSummaryOptions(preset) {
    const summary = await this._hass.callWS({
      type: "edata/ws/summary",
      scups: this._scups,
    });

    var p1 = undefined;
    var p2 = undefined;
    var p3 = undefined;
    var surplus = undefined;
    var cost = undefined;
    var date = new Date(summary["last_registered_date"]);

    switch (preset) {
      case "last-day":
        p1 = summary["last_registered_day_p1_kWh"];
        p2 = summary["last_registered_day_p2_kWh"];
        p3 = summary["last_registered_day_p3_kWh"];
        surplus = summary["last_registered_day_surplus_kWh"];
        this._bottom_right_value =
          date.getDate() +
          "/" +
          (date.getMonth() + 1) +
          "/" +
          date.getFullYear();
        break;
      case "last-month":
        p1 = summary["last_month_p1_kWh"];
        p2 = summary["last_month_p2_kWh"];
        p3 = summary["last_month_p3_kWh"];
        surplus = summary["last_month_surplus_kWh"];
        cost = summary["last_month_€"];
        date.setDate(0);
        this._bottom_right_value =
          date.getMonth() + 1 + "/" + date.getFullYear();
        break;
      case "month":
        p1 = summary["month_p1_kWh"];
        p2 = summary["month_p2_kWh"];
        p3 = summary["month_p3_kWh"];
        surplus = summary["month_surplus_kWh"];
        cost = summary["month_€"];
        this._bottom_right_value =
          date.getMonth() + 1 + "/" + date.getFullYear();
        break;
    }

    this._top_left_value = Math.round((p1 + p2 + p3) * 100) / 100;
    this._top_left_unit = DEF_ENERGY_UNIT;
    this._top_left_title = getLabel("total");
    this._bottom_right_unit = "";
    this._bottom_right_title = getLabel("date");

    if (surplus) {
      this._bottom_left_title = getLabel("surplus");
      this._bottom_left_value = surplus;
      this._bottom_left_unit = DEF_ENERGY_UNIT;
    }

    if (cost) {
      this._top_right_title = getLabel("cost");
      this._top_right_value = cost;
      this._top_right_unit = DEF_COST_UNIT;
    }

    var config = {
      chart: {
        id: "chart",
        type: "pie",
        width: 300,
      },
      colors: this._colors,
      series: [p1, p2, p3],
      labels: [getLabel("p1"), getLabel("p2"), getLabel("p3")],
      legend: {
        position: "bottom",
      },
    };

    if (this._aggr == "year") {
      config["xaxis"] = {
        tickAmount: "dataPoints",
        labels: {
          datetimeUTC: false,
          formatter: function (val) {
            return new Date(val).getFullYear().toString();
          },
        },
      };
    }

    return config;
  }

  normalizeX(list1, list2, list3) {
    const allX = new Set();

    list1.forEach(([x, _]) => allX.add(x));
    list2.forEach(([x, _]) => allX.add(x));
    list3.forEach(([x, _]) => allX.add(x));

    const sortedX = Array.from(allX).sort((a, b) => a - b);

    const mergeList = (list) => {
      const map = new Map(list);
      return sortedX.map((x) => [x, map.get(x) || 0]);
    };

    const newList1 = mergeList(list1);
    const newList2 = mergeList(list2);
    const newList3 = mergeList(list3);

    return [newList1, newList2, newList3];
  }

  async renderChart() {
    await this.updateComplete;

    console.log();

    if (!this._loaded && !this._chart) {
      this._loaded = true;
      var chartOptions;

      switch (this._template) {
        case "consumptions":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/consumptions",
            DEF_ENERGY_UNIT,
            ["p1", "p2", "p3"]
          );
          break;
        case "surplus":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/surplus",
            DEF_ENERGY_UNIT
          );
          break;
        case "costs":
          chartOptions = await this.getBarChartOptions(
            "edata/ws/costs",
            DEF_COST_UNIT,
            ["p1", "p2", "p3"]
          );
          break;
        case "maximeter":
          chartOptions = await this.getMaximeterChartOptions();
          break;
        case "summary-last-day":
          chartOptions = await this.getSummaryOptions("last-day");
          break;
        case "summary-month":
          chartOptions = await this.getSummaryOptions("month");
          break;
        case "summary-last-month":
          chartOptions = await this.getSummaryOptions("last-month");
          break;
      }

      this.render();
      this._chart = new ApexCharts(
        this.shadowRoot.querySelector("#chart"),
        chartOptions
      );
      this._chart.render();
    }
  }

  getCardSize() {
    return 3;
  }
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "edata-card",
  name: "edata",
  preview: true,
  description: "Visualize edata's data!",
  documentationURL: "https://github.com/Astharok/homeassistant-edata",
});

customElements.define("edata-card", EdataCard);

class EdataCardEditor extends LitElement {
  static get properties() {
    return {
      hass: {},
      _config: {},
    };
  }

  _valueChanged(ev) {
    if (!this._config || !this.hass) {
      return;
    }
    const _config = Object.assign({}, this._config);
    _config.title = ev.detail.value.title;
    _config.entity = ev.detail.value.entity;
    _config.chart = ev.detail.value.chart;
    _config.aggr = ev.detail.value.aggr;
    _config.records = ev.detail.value.records;

    this._config = _config;

    const event = new CustomEvent("config-changed", {
      detail: { config: _config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  setConfig(config) {
    this._config = config;
  }

  render() {
    if (!this.hass || !this._config) {
      return html``;
    }

    return html`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[
        { name: "title", selector: { text: {} } },
        {
          name: "entity",
          selector: {
            select: {
              options: Object.keys(this.hass.states).filter((entity) =>
                entity.startsWith("sensor.edata_")
              ),
              mode: "dropdown",
            },
          },
        },
        {
          name: "chart",
          selector: {
            select: { options: VALID_CHART_TEMPLATES, mode: "dropdown" },
          },
        },
        {
          name: "aggr",
          selector: {
            select: { options: VALID_AGGR_PERIODS, mode: "dropdown" },
          },
        },
        { name: "records", selector: { number: { min: 1, max: 365 } } },
      ]}
      .computeLabel=${this._computeLabel}
      @value-changed=${this._valueChanged}
    ></ha-form> `;
  }

  _computeLabel(schema) {
    return getLabel(schema.name);
  }
}

customElements.define("edata-card-editor", EdataCardEditor);

// ---------------------------------------------------------------------------
// edata-solar-card  —  Solar energy panel + real bill breakdown
// ---------------------------------------------------------------------------

class EdataSolarCard extends LitElement {
  constructor() {
    super();
    this._monthly = [];
    this._monthIdx = -1; // -1 = most recent
    this._charts = {};
  }

  static get properties() {
    return { hass: {}, config: {}, _monthly: [], _monthIdx: Number };
  }

  static getConfigElement() {
    return document.createElement("edata-solar-card-editor");
  }

  static getStubConfig() {
    return { entity: undefined, title: "Panel Solar" };
  }

  setConfig(config) {
    if (!config.entity?.startsWith("sensor.edata")) {
      throw new Error("Define a valid entity (sensor.edata_XXXX)");
    }
    this._scups = config.entity.split("_")[1];
    this._title = config.title || "Panel Solar";
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._fetched) {
      this._fetched = true;
      this._fetchData();
    }
  }

  async _fetchData() {
    try {
      this._monthly = await this._hass.callWS({
        type: "edata/consumptions/monthly",
        scups: this._scups,
      });
      this._monthIdx = this._monthly.length - 1;
      this.requestUpdate();
      await this.updateComplete;
      this._renderAllCharts();
    } catch (e) {
      console.error("edata-solar-card: fetch error", e);
    }
  }

  _fmtMonth(isoOrDate) {
    const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
    return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  }

  _fmtKwh(v) {
    if (v == null) return "—";
    return (+v).toFixed(1) + " kWh";
  }

  _fmtEur(v) {
    if (v == null) return "—";
    return (+v).toFixed(2) + " €";
  }

  _navPrev() {
    if (this._monthIdx > 0) {
      this._monthIdx--;
      this.requestUpdate();
      this._scheduleCharts();
    }
  }

  _navNext() {
    if (this._monthIdx < this._monthly.length - 1) {
      this._monthIdx++;
      this.requestUpdate();
      this._scheduleCharts();
    }
  }

  _scheduleCharts() {
    // Destroy existing charts so they redraw with fresh data
    Object.values(this._charts).forEach(c => { try { c.destroy(); } catch (_) {} });
    this._charts = {};
    this.updateComplete.then(() => this._renderAllCharts());
  }

  get _rec() {
    return this._monthly[this._monthIdx] || null;
  }

  // ------------------------------------------------------------------
  // Bill breakdown helpers
  // ------------------------------------------------------------------

  _billRows(rec) {
    if (!rec) return [];
    const et = rec.energy_term ?? null;
    const pt = rec.power_term ?? null;
    const st = rec.surplus_term ?? null;
    const ot = rec.others_term ?? null;
    const total = rec.value_eur ?? null;
    if (et == null && pt == null && total == null) return [];

    // Back-calculate IE and IVA from totals
    // BillingProcessor already embeds taxes; we recover subtotals for display.
    // Approximation: we assume energy_term and power_term are the pre-IVA+IE values.
    // Actually the formula is:  term = electricity_tax * iva_tax * base
    // We cannot know the exact multipliers here without the rules, so we just show the
    // computed amounts as-is from BillingProcessor (they already include taxes).
    const subtotalTerms = (et || 0) + (pt || 0) + (ot || 0);
    const surplusDiscount = st ? -Math.abs(st) : 0;
    const rows = [];
    if (pt != null) rows.push({ label: "Potencia (P1+P2)", value: pt, cls: "" });
    if (et != null) rows.push({ label: "Energía importada", value: et, cls: "" });
    if (st != null) rows.push({ label: "Compensación excedentes", value: surplusDiscount, cls: "surplus" });
    if (ot != null) rows.push({ label: "Alquiler contador", value: ot, cls: "" });
    if (total != null) rows.push({ label: "TOTAL FACTURA", value: total, cls: "total" });
    return rows;
  }

  _solarSaving(rec) {
    if (!rec) return null;
    // Saving ≈ energy_term × (self_consumption / value_kWh) + surplus_term
    const sc = rec.self_consumption_kWh || 0;
    const imp = rec.value_kWh || 0;
    const et = rec.energy_term;
    const st = rec.surplus_term;
    if (!et || !imp) return null;
    const avgRate = et / imp;
    return sc * avgRate + Math.abs(st || 0);
  }

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  render() {
    if (!this._monthly.length) {
      return html`<ha-card><div style="padding:16px;color:var(--secondary-text-color)">Cargando datos solares…</div></ha-card>`;
    }

    const rec = this._rec;
    const monthLabel = rec ? this._fmtMonth(rec.datetime) : "";
    const hasPrev = this._monthIdx > 0;
    const hasNext = this._monthIdx < this._monthly.length - 1;

    const imported = rec?.value_kWh ?? 0;
    const surplus = rec?.surplus_kWh ?? 0;
    const generation = rec?.generation_kWh ?? 0;
    const selfCons = rec?.self_consumption_kWh ?? 0;
    const totalHouse = imported + selfCons;

    const billRows = this._billRows(rec);
    const saving = this._solarSaving(rec);

    return html`
      <style>
        :host { display: block; }
        .card-header { padding: 16px 16px 0; font-size: 16px; font-weight: 500; color: var(--secondary-text-color); }
        .nav-row { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 8px 16px; }
        .nav-btn { background: none; border: none; cursor: pointer; color: var(--primary-text-color); font-size: 20px; padding: 4px 10px; border-radius: 50%; }
        .nav-btn:disabled { opacity: 0.3; cursor: default; }
        .month-label { font-size: 15px; font-weight: 500; min-width: 160px; text-align: center; }
        .kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 8px 16px; }
        .kpi-box { background: var(--secondary-background-color); border-radius: 8px; padding: 8px; text-align: center; }
        .kpi-val { font-size: 16px; font-weight: bold; }
        .kpi-lbl { font-size: 11px; color: var(--secondary-text-color); margin-top: 2px; }
        .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 8px 16px; }
        .donut-box { background: var(--secondary-background-color); border-radius: 8px; padding: 8px; }
        .donut-title { font-size: 12px; color: var(--secondary-text-color); text-align: center; margin-bottom: 4px; }
        .bill-section { padding: 8px 16px; }
        .bill-title { font-size: 13px; font-weight: 500; color: var(--secondary-text-color); margin-bottom: 6px; }
        .bill-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .bill-table td { padding: 4px 6px; }
        .bill-table td:last-child { text-align: right; font-weight: 500; }
        .bill-row-total td { border-top: 1px solid var(--divider-color); font-weight: bold; font-size: 14px; padding-top: 6px; }
        .bill-row-surplus td { color: #4caf50; }
        .saving-chip { display: inline-block; background: #1b5e20; color: #a5d6a7; border-radius: 16px; padding: 4px 12px; font-size: 12px; margin-left: 8px; }
        .history-section { padding: 8px 16px 16px; }
        .history-title { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 4px; }
        #donut-origin, #donut-dest, #hist-kwh, #hist-eur { width: 100%; }
        .no-solar { color: var(--secondary-text-color); font-size: 12px; text-align: center; padding: 8px; }
      </style>

      <ha-card>
        <div class="card-header">${this._title}</div>

        <!-- Month navigator -->
        <div class="nav-row">
          <button class="nav-btn" ?disabled=${!hasPrev} @click=${this._navPrev}>◀</button>
          <span class="month-label">${monthLabel}</span>
          <button class="nav-btn" ?disabled=${!hasNext} @click=${this._navNext}>▶</button>
        </div>

        <!-- KPI chips -->
        <div class="kpi-row">
          <div class="kpi-box">
            <div class="kpi-val">${(+imported).toFixed(1)}</div>
            <div class="kpi-lbl">Importado kWh</div>
          </div>
          <div class="kpi-box">
            <div class="kpi-val">${generation > 0 ? (+generation).toFixed(1) : "—"}</div>
            <div class="kpi-lbl">Producido kWh</div>
          </div>
          <div class="kpi-box">
            <div class="kpi-val">${selfCons > 0 ? (+selfCons).toFixed(1) : "—"}</div>
            <div class="kpi-lbl">Autoconsumo kWh</div>
          </div>
          <div class="kpi-box">
            <div class="kpi-val">${(+surplus).toFixed(1)}</div>
            <div class="kpi-lbl">Vertido kWh</div>
          </div>
        </div>

        <!-- Donut charts -->
        ${generation > 0 ? html`
        <div class="charts-row">
          <div class="donut-box">
            <div class="donut-title">Origen del consumo</div>
            <div id="donut-origin"></div>
          </div>
          <div class="donut-box">
            <div class="donut-title">Destino de la producción</div>
            <div id="donut-dest"></div>
          </div>
        </div>` : html`
        <div style="padding:8px 16px">
          <div class="no-solar">Sin datos solares para este mes (sidecar aún vacío o mes sin generación)</div>
        </div>`}

        <!-- Bill breakdown -->
        ${billRows.length ? html`
        <div class="bill-section">
          <div class="bill-title">
            Factura estimada
            ${saving != null ? html`<span class="saving-chip">☀ Ahorro solar: ${saving.toFixed(2)} €</span>` : ""}
          </div>
          <table class="bill-table">
            ${billRows.map(row => html`
              <tr class="${row.cls === "total" ? "bill-row-total" : row.cls === "surplus" ? "bill-row-surplus" : ""}">
                <td>${row.label}</td>
                <td>${this._fmtEur(row.value)}</td>
              </tr>
            `)}
          </table>
        </div>` : ""}

        <!-- Historical charts -->
        <div class="history-section">
          <div class="history-title">Histórico mensual — energía (kWh)</div>
          <div id="hist-kwh"></div>
          ${billRows.length ? html`
          <div class="history-title" style="margin-top:12px">Histórico mensual — factura (€)</div>
          <div id="hist-eur"></div>` : ""}
        </div>
      </ha-card>
    `;
  }

  // ------------------------------------------------------------------
  // ApexCharts rendering
  // ------------------------------------------------------------------

  async _renderAllCharts() {
    await this.updateComplete;
    const root = this.shadowRoot;
    const rec = this._rec;
    if (!rec) return;

    const imported = rec.value_kWh || 0;
    const selfCons = rec.self_consumption_kWh || 0;
    const surplus = rec.surplus_kWh || 0;
    const generation = rec.generation_kWh || 0;
    const totalHouse = imported + selfCons;

    const isDark = this._hass?.themes?.darkMode ?? false;
    const theme = isDark ? "dark" : "light";

    const baseOpts = {
      theme: { mode: theme },
      chart: { background: "transparent", toolbar: { show: false }, animations: { enabled: false } },
    };

    // --- Donut 1: origin of consumption ---
    const donutOriginEl = root.querySelector("#donut-origin");
    if (donutOriginEl && generation > 0 && !this._charts["donut-origin"]) {
      const pctImport = totalHouse > 0 ? ((imported / totalHouse) * 100).toFixed(1) : 0;
      const pctSelf = totalHouse > 0 ? ((selfCons / totalHouse) * 100).toFixed(1) : 0;
      const opts = {
        ...baseOpts,
        chart: { ...baseOpts.chart, type: "donut", height: 180 },
        series: [+imported, +selfCons],
        labels: [`Red (${pctImport}%)`, `Autoconsumo (${pctSelf}%)`],
        colors: ["#e54304", "#9ccc65"],
        dataLabels: { enabled: true, formatter: (_, opts) => (+opts.w.globals.series[opts.seriesIndex]).toFixed(1) + " kWh" },
        legend: { position: "bottom", fontSize: "11px" },
        plotOptions: { pie: { donut: { size: "60%" } } },
        tooltip: { y: { formatter: v => (+v).toFixed(1) + " kWh" } },
      };
      this._charts["donut-origin"] = new ApexCharts(donutOriginEl, opts);
      this._charts["donut-origin"].render();
    }

    // --- Donut 2: destination of production ---
    const donutDestEl = root.querySelector("#donut-dest");
    if (donutDestEl && generation > 0 && !this._charts["donut-dest"]) {
      const pctSelf = generation > 0 ? ((selfCons / generation) * 100).toFixed(1) : 0;
      const pctSurp = generation > 0 ? ((surplus / generation) * 100).toFixed(1) : 0;
      const opts = {
        ...baseOpts,
        chart: { ...baseOpts.chart, type: "donut", height: 180 },
        series: [+selfCons, +surplus],
        labels: [`Autoconsumo (${pctSelf}%)`, `Vertido (${pctSurp}%)`],
        colors: ["#9ccc65", "#ff9e22"],
        dataLabels: { enabled: true, formatter: (_, opts) => (+opts.w.globals.series[opts.seriesIndex]).toFixed(1) + " kWh" },
        legend: { position: "bottom", fontSize: "11px" },
        plotOptions: { pie: { donut: { size: "60%" } } },
        tooltip: { y: { formatter: v => (+v).toFixed(1) + " kWh" } },
      };
      this._charts["donut-dest"] = new ApexCharts(donutDestEl, opts);
      this._charts["donut-dest"].render();
    }

    // --- Historical bar chart: kWh ---
    const histKwhEl = root.querySelector("#hist-kwh");
    if (histKwhEl && !this._charts["hist-kwh"]) {
      const months = this._monthly;
      const cats = months.map(m => new Date(m.datetime).getTime());
      const hasSolar = months.some(m => (m.generation_kWh || 0) > 0);

      const seriesKwh = [
        { name: "Importado red", data: months.map(m => +(m.value_kWh || 0).toFixed(1)) },
        { name: "Autoconsumo", data: months.map(m => +(m.self_consumption_kWh || 0).toFixed(1)) },
        { name: "Vertido red", data: months.map(m => +(m.surplus_kWh || 0).toFixed(1)) },
      ];

      const opts = {
        ...baseOpts,
        chart: { ...baseOpts.chart, type: "bar", height: 180, stacked: true },
        series: seriesKwh,
        colors: ["#e54304", "#9ccc65", "#ff9e22"],
        xaxis: { type: "datetime", categories: cats, labels: { datetimeUTC: false, format: "MMM yy" } },
        yaxis: { title: { text: "kWh" }, labels: { formatter: v => v.toFixed(0) } },
        legend: { position: "top", fontSize: "11px" },
        tooltip: { y: { formatter: v => v.toFixed(1) + " kWh" } },
        dataLabels: { enabled: false },
      };
      this._charts["hist-kwh"] = new ApexCharts(histKwhEl, opts);
      this._charts["hist-kwh"].render();
    }

    // --- Historical bar chart: € ---
    const histEurEl = root.querySelector("#hist-eur");
    if (histEurEl && !this._charts["hist-eur"]) {
      const months = this._monthly.filter(m => m.value_eur != null);
      if (months.length) {
        const cats = months.map(m => new Date(m.datetime).getTime());
        const seriesEur = [
          { name: "Potencia", data: months.map(m => +(m.power_term || 0).toFixed(2)) },
          { name: "Energía", data: months.map(m => +(m.energy_term || 0).toFixed(2)) },
          { name: "Compensación excedentes", data: months.map(m => -(+(m.surplus_term || 0).toFixed(2))) },
          { name: "Contador", data: months.map(m => +(m.others_term || 0).toFixed(2)) },
        ];
        const opts = {
          ...baseOpts,
          chart: { ...baseOpts.chart, type: "bar", height: 180, stacked: true },
          series: seriesEur,
          colors: ["#e54304", "#ff9e22", "#9ccc65", "#aaa"],
          xaxis: { type: "datetime", categories: cats, labels: { datetimeUTC: false, format: "MMM yy" } },
          yaxis: { title: { text: "€" }, labels: { formatter: v => v.toFixed(0) } },
          legend: { position: "top", fontSize: "11px" },
          tooltip: { y: { formatter: v => v.toFixed(2) + " €" } },
          dataLabels: { enabled: false },
        };
        this._charts["hist-eur"] = new ApexCharts(histEurEl, opts);
        this._charts["hist-eur"].render();
      }
    }
  }

  getCardSize() { return 5; }
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "edata-solar-card",
  name: "edata Solar",
  preview: true,
  description: "Panel solar: diagramas de energía, factura real y histórico mensual",
  documentationURL: "https://github.com/Astharok/homeassistant-edata",
});

customElements.define("edata-solar-card", EdataSolarCard);

// Minimal editor for the solar card
class EdataSolarCardEditor extends LitElement {
  static get properties() { return { hass: {}, _config: {} }; }

  setConfig(config) { this._config = config; }

  _valueChanged(ev) {
    const _config = { ...this._config, ...ev.detail.value };
    this._config = _config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: _config }, bubbles: true, composed: true }));
  }

  render() {
    if (!this.hass || !this._config) return html``;
    return html`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[
        { name: "title", selector: { text: {} } },
        {
          name: "entity",
          selector: {
            select: {
              options: Object.keys(this.hass.states).filter(e => e.startsWith("sensor.edata_")),
              mode: "dropdown",
            },
          },
        },
      ]}
      @value-changed=${this._valueChanged}
    ></ha-form>`;
  }
}

customElements.define("edata-solar-card-editor", EdataSolarCardEditor);

