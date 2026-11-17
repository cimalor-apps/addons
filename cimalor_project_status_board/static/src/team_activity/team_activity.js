import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { formatFloat } from "@web/core/utils/numbers";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const { DateTime } = luxon;

// Widest bar of a day, in pixels, for a day of work at full capacity.
const BAR_WIDTH = 90;
// Day length used to draw bars when a person has no capacity that day.
const DEFAULT_DAY_HOURS = 8;
// How often the running timers move forward on screen, in milliseconds.
const TICK = 30000;

/**
 * Reporting › Team Activity: what each person is on now and what they did.
 *
 * One block per person: a header row with their running timer (live) and,
 * for each of the last working days, their hours against their capacity;
 * then one row per project with the hours of each day (at most five, the
 * rest added up as "other projects"). Timesheets store hours per day, not
 * times of day, so each day shows a total. The running timer adds a striped
 * piece to today on its project's row.
 *
 * The figures come from cimalor.project.activity, read when the view opens;
 * only the running timers move forward while it stays open.
 */
export class TeamActivity extends Component {
  static template = "cimalor_project_status_board.TeamActivity";
  static components = { Layout };
  static props = { ...standardActionServiceProps };

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.state = useState({ loading: true, data: null, now: Date.now() });
    this.loadedAt = Date.now();
    onWillStart(() => this.load());
    const interval = setInterval(() => (this.state.now = Date.now()), TICK);
    onWillUnmount(() => clearInterval(interval));
  }

  async load() {
    this.state.data = await this.orm.call(
      "cimalor.project.activity",
      "get_activity_data",
      [],
    );
    this.loadedAt = Date.now();
    this.state.loading = false;
  }

  get todayIndex() {
    return this.state.data.days.findIndex((day) => day.today);
  }

  dayName(day) {
    return DateTime.fromISO(day.date).toFormat("ccc d");
  }

  dayMonth(day) {
    return DateTime.fromISO(day.date).toFormat("LLL");
  }

  /** Hours of the running timer, moving forward while the view is open. */
  elapsed(person) {
    if (!person.timer) {
      return 0;
    }
    return person.timer.elapsed + (this.state.now - this.loadedAt) / 3600000;
  }

  /** When the running timer started, in milliseconds. */
  timerStart(person) {
    return this.loadedAt - person.timer.elapsed * 3600000;
  }

  midnight() {
    return DateTime.fromMillis(this.state.now).startOf("day").toMillis();
  }

  /**
   * Hours of the running timer that belong to today: a timer left running
   * since another day only counts from midnight.
   */
  elapsedToday(person) {
    if (!person.timer) {
      return 0;
    }
    const sinceMidnight = (this.state.now - this.midnight()) / 3600000;
    return Math.min(this.elapsed(person), Math.max(sinceMidnight, 0));
  }

  startedBeforeToday(person) {
    return this.timerStart(person) < this.midnight();
  }

  /** Hours of the running timer on a project row and day. */
  openHours(person, row, index) {
    return row.open && index === this.todayIndex
      ? this.elapsedToday(person)
      : 0;
  }

  loggedOn(person, index) {
    let total = person.rows.reduce((sum, row) => sum + row.hours[index], 0);
    if (person.others) {
      total += person.others.hours[index];
    }
    return total;
  }

  /** Everything of the day, the running timer included. */
  dayTotal(person, index) {
    const open = index === this.todayIndex ? this.elapsedToday(person) : 0;
    return this.loggedOn(person, index) + open;
  }

  total(person) {
    return this.state.data.days.reduce(
      (sum, day, index) => sum + this.dayTotal(person, index),
      0,
    );
  }

  totalCapacity(person) {
    return person.capacity.reduce((sum, hours) => sum + hours, 0);
  }

  rowTotal(row) {
    return row.hours.reduce((sum, hours) => sum + hours, 0);
  }

  hours(value) {
    return formatFloat(value, { digits: [16, 1], trailingZeros: false });
  }

  /** "1.5 h"; a few minutes, which would round to 0 h, as "4 min". */
  hoursText(value) {
    if (value > 0 && value < 0.1) {
      return _t("%(minutes)s min", {
        minutes: Math.max(Math.round(value * 60), 1),
      });
    }
    return _t("%(hours)s h", { hours: this.hours(value) });
  }

  dayText(person, index) {
    const open = index === this.todayIndex ? this.elapsedToday(person) : 0;
    const logged = this.loggedOn(person, index);
    if (open) {
      return _t("%(logged)s h + %(open)s h open", {
        logged: this.hours(logged),
        open: this.hours(open),
      });
    }
    return this.hoursText(logged);
  }

  rowText(person, row) {
    const open = this.openHours(person, row, this.todayIndex);
    const total = this.rowTotal(row);
    return this.hoursText(total + open);
  }

  cellText(person, row, index) {
    const logged = row.hours[index];
    const open = this.openHours(person, row, index);
    if (open && logged) {
      return `${this.hours(logged)} + ${this.hours(open)}`;
    }
    if (open) {
      return this.hoursText(open);
    }
    return logged ? this.hoursText(logged) : "";
  }

  /** Bar width for some hours of one day, at the person's capacity that day. */
  barWidth(person, index, value) {
    const dayHours = person.capacity[index] || DEFAULT_DAY_HOURS;
    return Math.min((value / dayHours) * BAR_WIDTH, BAR_WIDTH);
  }

  barStyle(person, index, value) {
    return `width: ${Math.max(this.barWidth(person, index, value), 3)}px;`;
  }

  /** The day's hours against the day's capacity, as a filled gauge. */
  gaugeStyle(person, index) {
    const capacity = person.capacity[index];
    const ratio = capacity ? this.dayTotal(person, index) / capacity : 0;
    return `width: ${Math.min(ratio, 1) * 100}%;`;
  }

  isFull(person, index) {
    const capacity = person.capacity[index];
    return capacity > 0 && this.dayTotal(person, index) >= capacity - 0.01;
  }

  elapsedText(person) {
    const minutes = Math.floor(this.elapsed(person) * 60);
    if (minutes < 60) {
      return _t("%(minutes)s min", { minutes });
    }
    return _t("%(hours)s h %(minutes)s min", {
      hours: Math.floor(minutes / 60),
      minutes: minutes % 60,
    });
  }

  nowText(person) {
    const timer = person.timer;
    const what = timer.project_id
      ? `${timer.project} · ${timer.task}`
      : timer.task;
    if (this.startedBeforeToday(person)) {
      // Most likely forgotten: say since when rather than a long duration.
      return _t("Now: %(what)s · running since %(date)s", {
        what,
        date: DateTime.fromMillis(this.timerStart(person)).toFormat(
          "d LLL HH:mm",
        ),
      });
    }
    return _t("Now: %(what)s · %(time)s", {
      what,
      time: this.elapsedText(person),
    });
  }

  /** "Last time entry today at 18:10", in the user's timezone. */
  lastEntryText(person) {
    if (!person.last_entry) {
      return _t("No timer running");
    }
    const when = DateTime.fromSQL(person.last_entry, { zone: "utc" }).setZone(
      "default",
    );
    const time = when.toFormat("HH:mm");
    const days = Math.round(
      DateTime.now().startOf("day").diff(when.startOf("day"), "days").days,
    );
    let moment;
    if (days === 0) {
      moment = _t("today at %(time)s", { time });
    } else if (days === 1) {
      moment = _t("yesterday at %(time)s", { time });
    } else {
      moment = _t("%(date)s at %(time)s", {
        date: when.toFormat("d LLL"),
        time,
      });
    }
    return _t("No timer running · last time entry %(moment)s", { moment });
  }

  othersText(person) {
    return _t("Other projects (%(count)s)", { count: person.others.count });
  }

  openProject(row) {
    const form = this.state.data.project_form_id;
    this.action.doAction({
      type: "ir.actions.act_window",
      res_model: "project.project",
      res_id: row.project_id,
      views: [[form || false, "form"]],
    });
  }
}

registry.category("actions").add("cimalor_project_team_activity", TeamActivity);
