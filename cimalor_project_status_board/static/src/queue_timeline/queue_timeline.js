import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const { DateTime } = luxon;

// Width of one day on the time axis, in pixels.
const DAY_WIDTH = 15;
// Days shown at least, and at most (about six months).
const MIN_DAYS = 28;
const MAX_DAYS = 200;

/**
 * Reporting › Queue by Person: each person's work queue on a time axis.
 *
 * One block per person: a header row with their capacity and a summary bar
 * of the whole queue, then one row per task in the order they work through
 * them (nearest due date first). Each task row holds its bar, from the day
 * it starts to the day it ends at the person's capacity, and its own due
 * date as a diamond, so there is no doubt which date belongs to which task.
 * A bar is red when the task ends after its due date. Due dates already
 * passed are written next to the bar; those beyond the axis at its edge.
 *
 * The figures come from cimalor.project.queue, the same queue as the days
 * margin, computed when the view opens. Odoo's Gantt view is Enterprise and
 * this module must work on Community: hence a small view of its own.
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

  /** Long enough for every queue and every due date, within the maximum. */
  get dayCount() {
    let last = 0;
    for (const person of this.state.data.people) {
      last = Math.max(last, person.last_end);
      for (const item of person.items) {
        if (item.deadline_offset !== null && item.deadline_offset < MAX_DAYS) {
          last = Math.max(last, item.deadline_offset + 1);
        }
      }
    }
    return Math.min(MAX_DAYS, Math.max(MIN_DAYS, Math.ceil(last) + 4));
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

  get weekends() {
    return this.days.filter((day) => day.weekend);
  }

  scheduled(person) {
    return person.items.filter((item) => item.start !== null);
  }

  clip(offset) {
    return offset === null ? this.dayCount : Math.min(offset, this.dayCount);
  }

  barStyle(item) {
    const left = item.start * DAY_WIDTH;
    const width = Math.max((this.clip(item.end) - item.start) * DAY_WIDTH, 4);
    return `left: ${left}px; width: ${width}px;`;
  }

  /** The light bar of a person's header row: from the first start to the last end. */
  summaryStyle(person) {
    const items = this.scheduled(person);
    if (!items.length) {
      return "display: none;";
    }
    const start = Math.min(...items.map((item) => item.start));
    const end = Math.max(...items.map((item) => this.clip(item.end)));
    const width = Math.max((end - start) * DAY_WIDTH, 4);
    return `left: ${start * DAY_WIDTH}px; width: ${width}px;`;
  }

  /** Where the due date goes: "diamond" on the axis, "passed", "beyond" or none. */
  deadlineKind(item) {
    if (item.deadline_offset === null) {
      return "none";
    }
    if (item.deadline_offset < 0) {
      return "passed";
    }
    return item.deadline_offset >= this.dayCount ? "beyond" : "diamond";
  }

  /** The diamond sits at the end of the due day. */
  diamondStyle(item) {
    return `left: ${(item.deadline_offset + 1) * DAY_WIDTH}px;`;
  }

  /** "Due date passed on 11 nov", written just after the bar. */
  passedStyle(item) {
    const end = item.start === null ? 0 : this.clip(item.end);
    return `left: ${end * DAY_WIDTH + 6}px;`;
  }

  passedText(item) {
    return _t("Due date passed on %(date)s", {
      date: this.shortDate(item.deadline),
    });
  }

  beyondText(item) {
    return `→ ${this.shortDate(item.deadline)}`;
  }

  hoursText(item) {
    return _t("%(hours)s h", { hours: item.hours });
  }

  barTitle(item) {
    const lines = [
      item.project,
      item.task,
      this.hoursText(item),
      item.end_date
        ? _t("Ends %(date)s", { date: this.formatDate(item.end_date) })
        : _t("Does not end within the next two years"),
    ];
    if (item.deadline) {
      lines.push(_t("Due %(date)s", { date: this.formatDate(item.deadline) }));
    }
    if (item.late) {
      lines.push(_t("Will be late"));
    }
    return lines.join("\n");
  }

  formatDate(isoDate) {
    return DateTime.fromISO(isoDate).toLocaleString(DateTime.DATE_MED);
  }

  shortDate(isoDate) {
    return DateTime.fromISO(isoDate).toFormat("d LLL");
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
