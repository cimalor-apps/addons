from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.tools import format_date, formatLang

MODULE = "cimalor_project_status_board"
BOARD_ACTION = f"{MODULE}.action_project_project"
ACTIVITY_ACTION = f"{MODULE}.action_cimalor_project_team_activity"


def action_url(base_url, action, record_id=None):
    """Link to an action of the board, or to one of its records (/odoo URLs)."""
    url = f"{base_url}/odoo/action-{action}"
    return f"{url}/{record_id}" if record_id else url


class CimalorProjectDigest(models.AbstractModel):
    """The daily email of the board: team activity, risks, overdue follow-ups.

    A scheduled job sends it to the people of Settings › Daily Email
    Recipients of each company, at the time of the job. Each person gets what
    they would see in the reports: the figures are read as them
    (with_user), so Team Activity shows only themselves unless they are
    Project administrators, and the projects follow Project's visibility.

    Mail clients run no JavaScript and keep little CSS, so the email does not
    reuse the Team Activity view: it is a QWeb template of tables with inline
    styles, built from the same data (cimalor.project.activity).
    """

    _name = "cimalor.project.digest"
    _description = "Project Status Board Daily Email"

    @api.model
    def _cron_send_daily_email(self):
        """Daily job: one email per recipient and company."""
        companies = self.env["res.company"].search(
            [("cimalor_digest_user_ids", "!=", False)]
        )
        for company in companies:
            for user in company.cimalor_digest_user_ids:
                # A person who cannot work in the company would only get an
                # access error; without an address, there is nowhere to send.
                if not user.active or not user.email or company not in user.company_ids:
                    continue
                self._send_to_user(user, company)

    def _send_to_user(self, user, company):
        """Render the email for `user` in `company` and queue it.

        The mail is created as superuser, like digest does: the recipient
        list is the administrator's choice, not the user's own action. The
        mail queue sends it with the outgoing mail server of the database.
        """
        values = self._email_values(user, company)
        lang_env = self.with_context(lang=user.lang).env
        body = lang_env["ir.qweb"]._render(
            f"{MODULE}.cimalor_project_digest_email", values
        )
        subject = lang_env._(
            "%(company)s: Project Status Board, %(date)s",
            company=company.name,
            date=values["date_text"],
        )
        self.env["mail.mail"].sudo().create(
            {
                "auto_delete": True,
                "body_html": body,
                "email_from": (
                    company.partner_id.email_formatted
                    or self.env.ref("base.user_root").email_formatted
                ),
                "email_to": user.email_formatted,
                "headers": {"X-Auto-Response-Suppress": "OOF"},
                "state": "outgoing",
                "subject": subject,
            }
        )

    def _email_values(self, user, company):
        """Everything the template shows, read with the recipient's rights."""
        me = (
            self.with_user(user)
            .with_company(company)
            .with_context(lang=user.lang, tz=user.tz or "UTC")
        )
        env = me.env
        today = fields.Date.context_today(me)
        base_url = company.get_base_url()
        at_risk = me._at_risk_values(base_url)
        overdue = me._overdue_values(today, base_url)
        return {
            "company": company,
            "user": user,
            "date_text": format_date(env, today, date_format="long"),
            "activity": me._activity_values(base_url),
            "at_risk": at_risk,
            "overdue": overdue,
            "at_risk_text": me._count_text(
                len(at_risk), me.env._("1 at risk"), me.env._("%(count)s at risk")
            ),
            "overdue_text": me._count_text(
                len(overdue),
                me.env._("1 follow-up overdue"),
                me.env._("%(count)s follow-ups overdue"),
            ),
            "board_url": action_url(base_url, BOARD_ACTION),
            "activity_url": action_url(base_url, ACTIVITY_ACTION),
        }

    def _count_text(self, count, one, many):
        """The singular text for one, the plural one (with %(count)s) otherwise."""
        return one if count == 1 else many.replace("%(count)s", str(count))

    # Team Activity ---------------------------------------------------------

    def _hours_text(self, value):
        """1.5 h, 2 h; a few minutes, which would round to 0 h, as 4 min."""
        if 0 < value < 0.1:
            return self.env._("%(minutes)s min", minutes=max(round(value * 60), 1))
        digits = 0 if round(value, 1) == round(value) else 1
        return self.env._(
            "%(hours)s h", hours=formatLang(self.env, value, digits=digits)
        )

    def _open_today(self, timer):
        """Hours of the running timer that belong to today, in the user's tz.

        A timer left running since another day only counts from midnight,
        as in the Team Activity view.
        """
        if not timer:
            return 0.0
        tz = pytz.timezone(self.env.context.get("tz") or "UTC")
        now = datetime.now(tz)
        midnight = tz.localize(datetime.combine(now.date(), time.min))
        since_midnight = (now - midnight).total_seconds() / 3600
        return min(timer["elapsed"], since_midnight)

    def _activity_values(self, base_url):
        """Team Activity as rows of text, ready for the email's tables."""
        data = self.env["cimalor.project.activity"].get_activity_data()
        days = [fields.Date.to_date(day["date"]) for day in data["days"]]
        today_index = next(
            (index for index, day in enumerate(data["days"]) if day["today"]), None
        )
        people = []
        for person in data["people"]:
            open_hours = self._open_today(person["timer"])
            hours_rows = [row["hours"] for row in person["rows"]]
            if person["others"]:
                hours_rows.append(person["others"]["hours"])
            day_cells = []
            for index, capacity in enumerate(person["capacity"]):
                total = sum(hours[index] for hours in hours_rows)
                if index == today_index:
                    total += open_hours
                day_cells.append(
                    {
                        "text": self._hours_text(total) if total else "–",
                        "capacity": self._hours_text(capacity) if capacity else "",
                        "full": capacity > 0 and total >= capacity - 0.01,
                        "today": index == today_index,
                    }
                )
            rows = []
            for row in person["rows"]:
                cells = []
                for index, hours in enumerate(row["hours"]):
                    extra = open_hours if row["open"] and index == today_index else 0
                    cells.append(
                        {
                            "text": (
                                self._hours_text(hours + extra) if hours + extra else ""
                            ),
                            "open": bool(extra),
                            "today": index == today_index,
                        }
                    )
                total = sum(row["hours"]) + (open_hours if row["open"] else 0)
                rows.append(
                    {
                        "name": row["project"],
                        "url": action_url(base_url, BOARD_ACTION, row["project_id"]),
                        "open": row["open"],
                        "cells": cells,
                        "total": self._hours_text(total),
                    }
                )
            others = False
            if person["others"]:
                hours = person["others"]["hours"]
                others = {
                    "name": self.env._(
                        "Other projects (%(count)s)", count=person["others"]["count"]
                    ),
                    "cells": [
                        {
                            "text": self._hours_text(value) if value else "",
                            "today": index == today_index,
                        }
                        for index, value in enumerate(hours)
                    ],
                    "total": self._hours_text(sum(hours)),
                }
            week_total = sum(sum(hours) for hours in hours_rows) + open_hours
            capacity_total = sum(person["capacity"])
            people.append(
                {
                    "name": person["name"],
                    "now": self._now_text(person),
                    "running": bool(person["timer"]),
                    "days": day_cells,
                    "rows": rows,
                    "others": others,
                    "total": self._hours_text(week_total),
                    "capacity": (
                        self._hours_text(capacity_total) if capacity_total else ""
                    ),
                }
            )
        return {
            "days": [
                {
                    "name": format_date(self.env, day, date_format="EEE d"),
                    "today": index == today_index,
                }
                for index, day in enumerate(days)
            ],
            "people": people,
        }

    def _now_text(self, person):
        timer = person["timer"]
        if timer:
            what = (
                f"{timer['project']} · {timer['task']}"
                if timer["project_id"]
                else timer["task"]
            )
            tz = pytz.timezone(self.env.context.get("tz") or "UTC")
            now = datetime.now(tz)
            start = now - timedelta(hours=timer["elapsed"])
            if start.date() < now.date():
                # Most likely forgotten: say since when, as the view does.
                return self.env._(
                    "Timer running since %(date)s at %(time)s: %(what)s",
                    date=format_date(self.env, start.date(), date_format="d MMM"),
                    time=start.strftime("%H:%M"),
                    what=what,
                )
            minutes = int(timer["elapsed"] * 60)
            elapsed = (
                self.env._("%(minutes)s min", minutes=minutes)
                if minutes < 60
                else self.env._(
                    "%(hours)s h %(minutes)s min",
                    hours=minutes // 60,
                    minutes=minutes % 60,
                )
            )
            return self.env._(
                "Timer running when this email was sent: %(what)s · %(time)s",
                what=what,
                time=elapsed,
            )
        if not person["last_entry"]:
            return self.env._("No time entries yet")
        when = fields.Datetime.context_timestamp(
            self, fields.Datetime.to_datetime(person["last_entry"])
        )
        return self.env._(
            "No timer running · last time entry %(date)s at %(time)s",
            date=format_date(self.env, when.date(), date_format="d MMM"),
            time=when.strftime("%H:%M"),
        )

    # Projects --------------------------------------------------------------

    def _project_domain(self):
        """Projects of the board: not excluded and not templates (19.0)."""
        return [("cimalor_excluded", "=", False), ("is_template", "=", False)]

    def _at_risk_values(self, base_url):
        """Projects that will need more hours or will be late.

        The board's own health (spec §4.6): hours margin or days margin
        negative. Finished and on-hold projects are left out, as in Reporting
        › Date Risk: they have no days margin.
        """
        projects = self.env["project.project"].search(
            self._project_domain()
            + [
                ("cimalor_state_type", "not in", ["done", "stopped"]),
                "|",
                ("cimalor_hours_health", "=", "over"),
                ("cimalor_days_health", "=", "late"),
            ],
            order="date, name",
        )
        rows = []
        for project in projects:
            hours_late = project.cimalor_hours_health == "over"
            days_late = project.cimalor_days_health == "late"
            rows.append(
                {
                    "name": project.display_name,
                    "url": action_url(base_url, BOARD_ACTION, project.id),
                    "manager": project.user_id.name or "",
                    "hours": (
                        self.env._(
                            "%(hours)s over",
                            hours=self._hours_text(-project.cimalor_hours_margin),
                        )
                        if hours_late
                        else ""
                    ),
                    "days": self._days_late_text(project) if days_late else "",
                    "late_by": project.cimalor_late_by or "",
                }
            )
        return rows

    def _days_late_text(self, project):
        if not project.cimalor_forecast_end_date:
            return self.env._("Late, no end in sight")
        days = -project.cimalor_days_margin
        text = self._count_text(
            days,
            self.env._("1 working day late (ends %(date)s)"),
            self.env._("%(count)s working days late (ends %(date)s)"),
        )
        return text % {
            "count": days,
            "date": format_date(
                self.env, project.cimalor_forecast_end_date, date_format="d MMM"
            ),
        }

    def _overdue_values(self, today, base_url):
        """Waiting projects whose follow-up date has passed."""
        projects = self.env["project.project"].search(
            self._project_domain()
            + [
                ("cimalor_state_type", "=", "waiting"),
                ("cimalor_follow_up_date", "<", today),
            ],
            order="cimalor_follow_up_date, name",
        )
        return [
            {
                "name": project.display_name,
                "url": action_url(base_url, BOARD_ACTION, project.id),
                "manager": project.user_id.name or "",
                "customer": project.partner_id.display_name or "",
                "reason": project._cimalor_reason_text() or "",
                "date": format_date(self.env, project.cimalor_follow_up_date),
                "ago": self._days_ago_text(
                    (today - project.cimalor_follow_up_date).days
                ),
            }
            for project in projects
        ]

    def _days_ago_text(self, days):
        if days == 1:
            return self.env._("yesterday")
        return self.env._("%(days)s days ago", days=days)
