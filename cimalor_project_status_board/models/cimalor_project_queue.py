from collections import defaultdict
from datetime import date, datetime, time, timedelta

from pytz import utc

from odoo import models

# Capacity is read from the schedules in steps of this many days, up to the
# limit: work beyond it is reported as not arriving, without a date.
STEP_DAYS = 120
LIMIT_DAYS = 730

# Sorts after any real date: tasks without a due date go to the end of the
# queue, and work beyond the limit "ends" here.
NEVER = date.max


class CimalorProjectQueue(models.AbstractModel):
    """The work queue of each person (spec §4.7 and §4.8), shared by the
    Capacity report and the days margin of the projects.

    Each working day, each person works on their available task with the
    nearest due date until their capacity for the day is used up. Ordering
    by due date is the best order to meet them: if a task is late with it,
    no other order gets everything on time.

    The rows are those of the Workload report (open main tasks, hours split
    among the assignees, unassigned to the project manager). Projects on hold
    are left out of the queue; waiting ones count from today.

    Nothing is stored: the queue depends on every project of every person
    involved, which @api.depends cannot follow, so it is computed when read.
    """

    _name = "cimalor.project.queue"
    _description = "Project Work Queue"

    def _employees_by_user(self, users):
        """The employee of each user, preferring one with a working schedule."""
        employees = (
            self.env["hr.employee"]
            .sudo()
            .search([("user_id", "in", users.ids)], order="id")
        )
        result = {}
        for employee in employees:
            current = result.get(employee.user_id.id)
            if not current or (
                not current.resource_calendar_id and employee.resource_calendar_id
            ):
                result[employee.user_id.id] = employee
        return result

    def _logged_today(self, users, today):
        """Hours each person has already logged on projects today."""
        groups = (
            self.env["account.analytic.line"]
            .sudo()
            ._read_group(
                [
                    ("user_id", "in", users.ids),
                    ("project_id", "!=", False),
                    ("date", "=", today),
                ],
                groupby=["user_id"],
                aggregates=["unit_amount:sum"],
            )
        )
        return {user.id: hours for user, hours in groups}

    def _daily_capacity(self, employee, start, stop):
        """Hours available for tasks on each day from start to stop, as {date: hours}.

        Odoo's own work intervals of the schedule, which already leave out
        the resource leaves (approved time off and public holidays), in the
        person's timezone; then the admin time of each working day, never
        below zero. Days without work are absent.
        """
        start_dt = datetime.combine(start, time.min).replace(tzinfo=utc)
        stop_dt = datetime.combine(stop, time.min).replace(tzinfo=utc)
        resource = employee.resource_id
        intervals = employee.resource_calendar_id._work_intervals_batch(
            start_dt, stop_dt, resources=resource
        )[resource.id]
        worked = defaultdict(float)
        for begin, end, _meta in intervals:
            worked[begin.date()] += (end - begin).total_seconds() / 3600
        admin = employee.cimalor_admin_hours
        return {
            day: max(hours - admin, 0.0)
            for day, hours in worked.items()
            if start <= day < stop
        }

    def _capacity_days(self, employee, today, logged_today):
        """Yield (day, hours) for each working day from today, up to the limit.

        Today only offers what is left after the hours already logged today.
        """
        start = today
        while (start - today).days < LIMIT_DAYS:
            stop = start + timedelta(days=STEP_DAYS)
            for day, hours in sorted(
                self._daily_capacity(employee, start, stop).items()
            ):
                if day == today:
                    hours = max(hours - logged_today, 0.0)
                if hours > 0:
                    yield day, hours
            start = stop

    def _finish_dates(self, employee, today, logged_today, hours_list):
        """Day each piece of work ends, consumed in the given order.

        `hours_list` is the hours of each piece in queue order; the result is
        a list of dates in the same order, NEVER for work beyond the limit.
        """
        days = self._capacity_days(employee, today, logged_today)
        day, available = next(days, (NEVER, 0.0))
        finishes = []
        for hours in hours_list:
            need = hours
            while day != NEVER and need > available + 1e-6:
                need -= available
                day, available = next(days, (NEVER, 0.0))
            # Work of zero hours is done where the queue stands.
            available = max(available - need, 0.0)
            finishes.append(day)
        return finishes

    def _queue_end_dates(self, user_hours, today):
        """Day each person's pending hours are used up, as {user id: date}.

        `user_hours` is {user id: hours}. The order of the tasks does not
        change when the whole queue ends, so one block of hours is enough.
        False for people without employee or working schedule.
        """
        users = self.env["res.users"].browse(list(user_hours))
        employees = self._employees_by_user(users)
        logged = self._logged_today(users, today)
        ends = {}
        for user_id, hours in user_hours.items():
            employee = employees.get(user_id)
            if not employee or not employee.resource_calendar_id:
                ends[user_id] = False
                continue
            ends[user_id] = self._finish_dates(
                employee, today, logged.get(user_id, 0.0), [hours]
            )[0]
        return ends

    def _project_forecast(self, today):
        """Forecast end of every project in the queue.

        Returns {project id: {"end": date or NEVER or False, "users":
        {user id: date or NEVER or False}}}: "end" is when its last open
        task ends (False when a person on it has no working schedule, so it
        cannot be known); "users" maps each person to the day their part of
        the project ends, to tell who the project waits for.
        """
        # The report reads a database view: write pending ORM changes first.
        self.env.flush_all()
        rows = (
            self.env["cimalor.project.workload.report"]
            .sudo()
            .search([("state_type", "!=", "stopped"), ("user_id", "!=", False)])
        )
        by_user = defaultdict(list)
        for row in rows:
            by_user[row.user_id].append(row)
        employees = self._employees_by_user(rows.user_id)
        logged = self._logged_today(rows.user_id, today)

        forecast = defaultdict(lambda: {"end": None, "users": {}})
        for user, user_rows in by_user.items():
            user_rows.sort(
                key=lambda row: (
                    row.date or NEVER,
                    -int(row.task_id.priority or 0),
                    row.project_id.sequence,
                    row.task_id.id,
                )
            )
            employee = employees.get(user.id)
            if employee and employee.resource_calendar_id:
                finishes = self._finish_dates(
                    employee,
                    today,
                    logged.get(user.id, 0.0),
                    [row.hours for row in user_rows],
                )
            else:
                finishes = [False] * len(user_rows)
            for row, finish in zip(user_rows, finishes, strict=True):
                project = forecast[row.project_id.id]
                users = project["users"]
                if finish is False or users.get(user.id) is False:
                    users[user.id] = False
                else:
                    users[user.id] = max(users.get(user.id) or finish, finish)
        for project in forecast.values():
            ends = list(project["users"].values())
            project["end"] = False if False in ends else max(ends)
        return forecast

    def _working_days_margin(self, calendar, end, due):
        """Working days from the forecast end to the due date (spec §4.8).

        Ending the working day before the due date gives +1, the same day 0,
        one working day later -1. Counted on the company's schedule, public
        holidays included; plain weekdays without a schedule.
        """
        if end == due:
            return 0
        first, last, sign = (end, due, 1) if end < due else (due, end, -1)
        start, stop = first + timedelta(days=1), last + timedelta(days=1)
        if calendar:
            start_dt = datetime.combine(start, time.min).replace(tzinfo=utc)
            stop_dt = datetime.combine(stop, time.min).replace(tzinfo=utc)
            intervals = calendar._work_intervals_batch(start_dt, stop_dt)[False]
            days = {begin.date() for begin, _end, _meta in intervals}
            count = len([day for day in days if start <= day < stop])
        else:
            count = sum(
                1
                for offset in range((stop - start).days)
                if (start + timedelta(days=offset)).weekday() < 5
            )
        return sign * count
