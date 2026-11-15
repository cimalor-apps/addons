import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const { DateTime } = luxon;

// Width of one day on the time axis, in pixels.
const DAY_WIDTH = 26;
// Days shown at least, and at most (the queue itself looks two years ahead).
const MIN_DAYS = 28;
const MAX_DAYS = 200;

/**
 * Reporting › Queue by Person: each person's work queue on a time axis.
 *
 * One row per person, one bar per task in the order they work through them
 * (nearest due date first), from the day it starts to the day it ends at
 * their capacity. A bar is red when the task ends after its due date, which
 * is marked on the row. The figures come from cimalor.project.queue, the
 * same queue as the days margin, computed when the view opens.
 *
 * Odoo's Gantt view is Enterprise, and this module must work on Community:
 * hence a small view of its own, read only.
 */
export class QueueTimeline extends Component {
  static template = "cimalor_project_status_board.QueueTimeline";
  static components = { Layout };
  static props = { ...standardActionServiceProps };

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.dayWidth = DAY_WIDTH;
    this.state = useState({ loading: true, data: null });
    onWillStart(() => this.load());
  }

  async load() {
    this.state.data = await this.orm.call(
      "cimalor.project.queue",
      "get_timeline_data",
      [],
    );
    this.state.loading = false;
  }

  get today() {
    return DateTime.fromISO(this.state.data.today);
  }

  get dayCount() {
    const lastEnd = Math.max(
      0,
      ...this.state.data.people.map((p) => p.last_end),
    );
    return Math.min(MAX_DAYS, Math.max(MIN_DAYS, Math.ceil(lastEnd) + 7));
  }

  get width() {
    return this.dayCount * DAY_WIDTH;
  }

  /** One entry per day of the axis, for the header and the weekend shading. */
  get days() {
    const days = [];
    for (let index = 0; index < this.dayCount; index++) {
      const day = this.today.plus({ days: index });
      days.push({
        index,
        left: index * DAY_WIDTH,
        weekend: day.weekday > 5,
        letter: day.toFormat("ccccc"),
        number: day.day,
        // A label at each Monday: "16 nov". The first day gets one too
        // when there is room before the next Monday (Monday to Thursday).
        label:
          day.weekday === 1 || (index === 0 && day.weekday <= 4)
            ? day.toFormat("d LLL")
            : "",
      });
    }
    return days;
  }

  barStyle(item) {
    const end =
      item.end === null ? this.dayCount : Math.min(item.end, this.dayCount);
    const left = item.start * DAY_WIDTH;
    const width = Math.max((end - item.start) * DAY_WIDTH, 4);
    return `left: ${left}px; width: ${width}px;`;
  }

  /** Due date marker, at the end of the due day. Hidden off the axis. */
  deadlineStyle(item) {
    if (item.deadline_offset === null || item.deadline_offset < 0) {
      return "display: none;";
    }
    if (item.deadline_offset >= this.dayCount) {
      return "display: none;";
    }
    return `left: ${(item.deadline_offset + 1) * DAY_WIDTH - 2}px;`;
  }

  barTitle(item) {
    const lines = [
      item.project,
      item.task,
      _t("%(hours)s h", { hours: item.hours }),
      item.end_date
        ? _t("Ends %(date)s", { date: this.formatDate(item.end_date) })
        : _t("Does not end within the next two years"),
    ];
    if (item.deadline) {
      lines.push(_t("Due %(date)s", { date: this.formatDate(item.deadline) }));
    }
    if (item.late) {
      lines.push(_t("Late"));
    }
    return lines.join("\n");
  }

  formatDate(isoDate) {
    return DateTime.fromISO(isoDate).toLocaleString(DateTime.DATE_MED);
  }

  scheduled(person) {
    return person.items.filter((item) => item.start !== null);
  }

  openProject(item) {
    const form = this.state.data.project_form_id;
    this.action.doAction({
      type: "ir.actions.act_window",
      res_model: "project.project",
      res_id: item.project_id,
      views: [[form || false, "form"]],
    });
  }
}

registry
  .category("actions")
  .add("cimalor_project_queue_timeline", QueueTimeline);
