from collections import defaultdict
from datetime import datetime, time, timedelta

from pytz import utc

from odoo import fields, models, tools
from odoo.tools import SQL

# The queue end is searched in steps of this many days, up to the limit: a
# person with years of work gets no date rather than a slow report.
QUEUE_STEP_DAYS = 120
QUEUE_LIMIT_DAYS = 730


class CimalorProjectCapacityReport(models.Model):
    """Reporting › Capacity: how long the pending work of each person takes.

    One row per employee with a user. The hours come from the Workload
    report (same rules: open main tasks, split among assignees, unassigned to
    the project manager), in two figures: pending hours (To Start, In
    Progress, Waiting) and on-hold hours, which are shown apart and do not
    count for the queue (spec §4.7).

    The capacity (spec §4.7) is the person's working schedule minus the
    approved time off and the public holidays (both are resource leaves in
    Odoo: Time Off creates them when a leave is approved, so they count
    without depending on that app) minus the admin time of each working day.

    The end of the queue does not depend on the order of the tasks, only on
    the hours and the capacity: it is the day the pending hours are used up,
    starting today with what is left of today's capacity. Which task arrives
    late, and the days margin of each project, need the order and come
    later with the queue of §4.8. Waiting tasks count from today: the
    follow-up date is not taken into account yet.

    The figures are computed when read, never stored: they follow the
    schedule, the leaves and the tasks as they are now.
    """

    _name = "cimalor.project.capacity.report"
    _description = "Capacity Analysis"
    _auto = False
    _order = "user_id"

    user_id = fields.Many2one(comodel_name="res.users", string="Person", readonly=True)
    employee_id = fields.Many2one(comodel_name="hr.employee", readonly=True)
    company_id = fields.Many2one(comodel_name="res.company", readonly=True)
    pending_hours = fields.Float(
        readonly=True,
        help="Hours left on the open tasks of projects to start, in progress or "
        "waiting.",
    )
    paused_hours = fields.Float(
        string="On Hold Hours",
        readonly=True,
        help="Hours left on the open tasks of projects on hold. They do not "
        "count for the end of the queue.",
    )
    # compute_sudo: employees, schedules, leaves and timesheets are HR data a
    # Project user may not read. Only the figures leave the computation, and
    # the record rules already limit the rows to the user's own.
    daily_capacity = fields.Float(
        compute="_compute_capacity",
        compute_sudo=True,
        help="Average hours per working day of the schedule, minus the admin time.",
    )
    weekly_capacity = fields.Float(
        compute="_compute_capacity",
        compute_sudo=True,
    )
    weeks_of_work = fields.Float(
        string="Weeks of Work",
        compute="_compute_capacity",
        compute_sudo=True,
        help="Pending hours over the weekly capacity.",
    )
    queue_end_date = fields.Date(
        string="Queue Ends",
        compute="_compute_capacity",
        compute_sudo=True,
        help="Day the pending hours are used up at the person's capacity, time "
        "off and holidays included. Empty without a working schedule.",
    )

    def _query(self):
        """One row per active employee with a user, with their workload.

        The Workload report's query is used as a subquery, so both reports
        apply the same rules. Employees without pending work are listed too:
        free capacity is worth seeing. Static SQL, as in the Workload report.
        """
        return SQL(
            """
            SELECT
                employee.id AS id,
                employee.user_id AS user_id,
                employee.id AS employee_id,
                employee.company_id AS company_id,
                COALESCE(SUM(workload.hours)
                    FILTER (WHERE workload.state_type IS DISTINCT FROM 'stopped'), 0)
                    AS pending_hours,
                COALESCE(SUM(workload.hours)
                    FILTER (WHERE workload.state_type = 'stopped'), 0) AS paused_hours
            FROM hr_employee AS employee
            JOIN res_users AS person ON person.id = employee.user_id
            LEFT JOIN (%s) AS workload
                ON workload.user_id = employee.user_id
                AND (workload.company_id = employee.company_id
                    OR workload.company_id IS NULL)
            WHERE employee.active AND person.active
            GROUP BY employee.id, employee.user_id, employee.company_id
            """,
            self.env["cimalor.project.workload.report"]._query(),
        )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            SQL(
                "CREATE OR REPLACE VIEW %s AS (%s)",
                SQL.identifier(self._table),
                self._query(),
            )
        )

    def _compute_capacity(self):
        today = fields.Date.context_today(self)
        for row in self:
            calendar = row.employee_id.resource_calendar_id
            admin = row.employee_id.cimalor_admin_hours
            daily = max(calendar.hours_per_day - admin, 0.0) if calendar else 0.0
            # Working days per week of the schedule, to scale the admin time.
            days_per_week = (
                calendar.hours_per_week / calendar.hours_per_day
                if calendar and calendar.hours_per_day
                else 0.0
            )
            row.daily_capacity = daily
            row.weekly_capacity = daily * days_per_week
            row.weeks_of_work = (
                row.pending_hours / row.weekly_capacity if row.weekly_capacity else 0.0
            )
        ends = self._cimalor_queue_end_dates(today)
        for row in self:
            row.queue_end_date = ends.get(row.id, False)

    def _cimalor_queue_end_dates(self, today):
        """Day each row's pending hours are used up, as {row id: date}.

        Today only counts what is left after the hours already logged today,
        as the queue of §4.8 will. Rows without pending hours end today; rows
        without a schedule, or not done within the limit, get no date.
        """
        ends = {row.id: today for row in self if row.pending_hours <= 0}
        left = {row.id: row.pending_hours for row in self if row.pending_hours > 0}
        logged = self._cimalor_logged_today(today)
        rows = self.filtered(
            lambda row: row.id in left and row.employee_id.resource_calendar_id
        )
        start = today
        while rows and (start - today).days < QUEUE_LIMIT_DAYS:
            stop = start + timedelta(days=QUEUE_STEP_DAYS)
            capacity = rows._cimalor_daily_capacity(start, stop)
            for row in rows:
                for day, hours in sorted(capacity[row.id].items()):
                    if day == today:
                        hours = max(hours - logged.get(row.user_id.id, 0.0), 0.0)
                    left[row.id] -= hours
                    if left[row.id] <= 0:
                        ends[row.id] = day
                        break
            rows = rows.filtered(lambda row: row.id not in ends)
            start = stop
        return ends

    def _cimalor_daily_capacity(self, start, stop):
        """Hours available for tasks on each day, as {row id: {date: hours}}.

        Odoo's own work intervals of the schedule, which already leave out
        the resource leaves (approved time off and public holidays), in each
        person's timezone; then the admin time of each working day, never
        below zero. Days without work are absent.
        """
        start_dt = datetime.combine(start, time.min).replace(tzinfo=utc)
        stop_dt = datetime.combine(stop, time.min).replace(tzinfo=utc)
        by_calendar = defaultdict(lambda: self.browse())
        for row in self:
            by_calendar[row.employee_id.resource_calendar_id] |= row
        result = {}
        for calendar, rows in by_calendar.items():
            intervals = calendar._work_intervals_batch(
                start_dt, stop_dt, resources=rows.employee_id.resource_id
            )
            for row in rows:
                worked = defaultdict(float)
                for begin, end, _meta in intervals[row.employee_id.resource_id.id]:
                    worked[begin.date()] += (end - begin).total_seconds() / 3600
                admin = row.employee_id.cimalor_admin_hours
                result[row.id] = {
                    day: max(hours - admin, 0.0)
                    for day, hours in worked.items()
                    if day >= start
                }
        return result

    def _cimalor_logged_today(self, today):
        """Hours each person has already logged on projects today."""
        groups = self.env["account.analytic.line"]._read_group(
            [
                ("user_id", "in", self.user_id.ids),
                ("project_id", "!=", False),
                ("date", "=", today),
            ],
            groupby=["user_id"],
            aggregates=["unit_amount:sum"],
        )
        return {user.id: hours for user, hours in groups}
