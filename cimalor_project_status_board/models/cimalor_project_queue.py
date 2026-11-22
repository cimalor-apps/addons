from collections import defaultdict
from datetime import date, datetime, time, timedelta

from pytz import utc

from odoo import api, fields, models

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

    def _schedule(self, employee, today, logged_today, hours_list):
        """Where each piece of work starts and ends, consumed in the given order.

        `hours_list` is the hours of each piece in queue order. Each result is
        (start day, start fraction, end day, end fraction): the fraction is
        the share of that day's capacity already used, so the pieces of one
        person follow each other without overlapping, even within a day.
        Work beyond the limit ends on NEVER. A piece of zero hours starts and
        ends where the queue stands.
        """
        days = self._capacity_days(employee, today, logged_today)
        day, capacity = next(days, (NEVER, 0.0))
        used = 0.0
        pieces = []
        for hours in hours_list:
            if day != NEVER and hours > 0 and used >= capacity - 1e-6:
                day, capacity = next(days, (NEVER, 0.0))
                used = 0.0
            if day == NEVER:
                pieces.append((NEVER, 0.0, NEVER, 0.0))
                continue
            start = (day, used / capacity)
            need = hours
            while day != NEVER and need > capacity - used + 1e-6:
                need -= capacity - used
                day, capacity = next(days, (NEVER, 0.0))
                used = 0.0
            if day == NEVER:
                pieces.append((*start, NEVER, 0.0))
                continue
            used = min(used + need, capacity)
            pieces.append((*start, day, used / capacity))
        return pieces

    def _finish_dates(self, employee, today, logged_today, hours_list):
        """Day each piece of work ends, consumed in the given order.

        `hours_list` is the hours of each piece in queue order; the result is
        a list of dates in the same order, NEVER for work beyond the limit.
        """
        return [
            piece[2]
            for piece in self._schedule(employee, today, logged_today, hours_list)
        ]

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
            self._sort_queue(user_rows)
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

    def _sort_queue(self, rows):
        """Order one person's workload rows as they work through them (§4.8).

        Nearest due date first; on the same date, task priority, then the
        project's sequence, then the oldest task. Rows without a date go last.
        """
        rows.sort(
            key=lambda row: (
                row.date or NEVER,
                -int(row.task_id.priority or 0),
                row.project_id.sequence,
                row.task_id.id,
            )
        )
        return rows

    @api.model
    def get_timeline_data(self):
        """The queue of each person, project by project, for Queue by Person.

        Public (called by the timeline view), but it only reads the Workload
        report with the user's own rights: each person sees their own queue
        and Project administrators everybody's, as in Workload and Capacity.
        A person's rows are always complete, so their queue is the real one.
        Projects on hold are left out, as in the queue itself, and so are the
        people of Settings › Employees Left Out of the Reports.

        The queue is still scheduled task by task, in the same order as the
        days margin; the tasks of one project are then gathered in one row,
        in the order the person reaches each project. Positions are in days
        from today: `segments` are the stretches the person works on the
        project, fractions of a day included (gaps when tasks of other
        projects come in between), from `start` to `end`. A project is late
        for that person when their part ends after its delivery date, the
        same rule as the days margin.
        """
        today = fields.Date.context_today(self)
        self.env.flush_all()
        rows = self.env["cimalor.project.workload.report"].search(
            [
                ("state_type", "!=", "stopped"),
                ("user_id", "!=", False),
                ("user_excluded", "=", False),
            ]
        )
        by_user = defaultdict(list)
        for row in rows:
            by_user[row.user_id].append(row)
        employees = self._employees_by_user(rows.user_id)
        logged = self._logged_today(rows.user_id, today)

        def offset(day, fraction):
            return None if day == NEVER else (day - today).days + fraction

        people = []
        for user in sorted(by_user, key=lambda user: user.name or ""):
            user_rows = self._sort_queue(by_user[user])
            employee = employees.get(user.id)
            calendar = employee.resource_calendar_id if employee else False
            if calendar:
                pieces = self._schedule(
                    employee,
                    today,
                    logged.get(user.id, 0.0),
                    [row.hours for row in user_rows],
                )
            else:
                pieces = [None] * len(user_rows)
            items = self._timeline_projects(user_rows, pieces, today, offset)
            ends = [item["end"] for item in items if item["end"] is not None]
            people.append(
                {
                    "user_id": user.id,
                    "name": user.name,
                    "has_schedule": bool(calendar),
                    "daily_capacity": (
                        max(calendar.hours_per_day - employee.cimalor_admin_hours, 0.0)
                        if calendar
                        else 0.0
                    ),
                    "late_count": sum(item["late"] for item in items),
                    "items": items,
                    "last_end": max(ends) if ends else 0,
                }
            )
        form = self.env.ref(
            "cimalor_project_status_board.view_project_project_form",
            raise_if_not_found=False,
        )
        return {
            "today": fields.Date.to_string(today),
            "people": people,
            "project_form_id": form.id if form else False,
        }

    def _timeline_projects(self, user_rows, pieces, today, offset):
        """Gather one person's scheduled tasks in one row per project.

        `pieces` are the task schedules from _schedule, in queue order (None
        when the person has no working schedule). A project ends with its last
        task: never, if any task does not end within the limit.
        """
        projects = {}
        previous = None
        for row, piece in zip(user_rows, pieces, strict=True):
            project = row.project_id
            item = projects.get(project.id)
            if item is None:
                item = projects[project.id] = {
                    "project_id": project.id,
                    "project": project.display_name,
                    "hours": 0.0,
                    "task_count": 0,
                    "segments": [],
                    "end_day": None,
                    "delivery": project.date,
                }
            item["hours"] += row.hours
            item["task_count"] += 1
            follows, previous = previous == project.id, project.id
            if not piece:
                continue
            start, end = offset(*piece[:2]), offset(*piece[2:])
            segments = item["segments"]
            # Tasks one after the other in the queue make one stretch of work,
            # weekends included; another project in between leaves a gap.
            if segments and follows:
                segments[-1]["end"] = end
            else:
                segments.append({"start": start, "end": end})
            if item["end_day"] != NEVER:
                item["end_day"] = max(item["end_day"] or piece[2], piece[2])

        items = []
        for item in projects.values():
            segments, end_day = item.pop("segments"), item.pop("end_day")
            delivery = item.pop("delivery")
            ends = [segment["end"] for segment in segments]
            item.update(
                {
                    "hours": round(item["hours"], 2),
                    "segments": segments,
                    "start": segments[0]["start"] if segments else None,
                    "end": None if None in ends else max(ends, default=None),
                    "end_date": (
                        fields.Date.to_string(end_day)
                        if end_day and end_day != NEVER
                        else False
                    ),
                    "deadline": fields.Date.to_string(delivery) if delivery else False,
                    "deadline_offset": (delivery - today).days if delivery else None,
                    "late": bool(delivery and end_day and end_day > delivery),
                }
            )
            items.append(item)
        return items

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
