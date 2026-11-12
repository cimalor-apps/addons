import { Component, onWillDestroy, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// Odoo loads luxon as a global; the web client reads it the same way.
const { DateTime } = luxon;

function formatElapsed(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

/**
 * Live counter for a datetime field holding when a timer started.
 *
 * The record only knows the start; the counter is "now minus start",
 * recomputed every second. Unlike adding one second per tick (as Odoo's
 * mrp_timer does), this stays right after the computer sleeps or the tab
 * is throttled, without a second timer to catch up.
 */
export class CimalorTimerField extends Component {
  static template = "cimalor_project_status_board.TimerField";
  static props = standardFieldProps;

  setup() {
    this.state = useState({ now: DateTime.now() });
    this.interval = setInterval(() => {
      this.state.now = DateTime.now();
    }, 1000);
    onWillDestroy(() => clearInterval(this.interval));
  }

  get elapsed() {
    const start = this.props.record.data[this.props.name];
    if (!start) {
      return "";
    }
    const seconds = Math.floor(this.state.now.diff(start, "seconds").seconds);
    return formatElapsed(Math.max(seconds, 0));
  }
}

export const cimalorTimerField = {
  component: CimalorTimerField,
  supportedTypes: ["datetime"],
};

registry.category("fields").add("cimalor_timer", cimalorTimerField);
