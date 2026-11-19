from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models

# Days shown: today and the working days before it.
DAY_COUNT = 5
# Project rows per person; the rest are added up in one "other projects" row.
MAX_PROJECTS = 5
# Monday to Friday, when the company has no working schedule.
DEFAULT_WORKING_WEEKDAYS = {0, 1, 2, 3, 4}


class CimalorProjectActivity(models.AbstractModel):
    """Reporting › Team Activity: what each person is on now and what they did.

    "Now" is the running timer of the module (cimalor.project.timer); what
    they did is their timesheets of the last working days, by project and day.
    Timesheets store hours per day, not times of day: each day is a total.
    """

    _name = "cimalor.project.activity"
    _description = "Team Activity"

    def _activity_days(self, today):
        """Today and the working days before it, oldest first.

        Working days are the weekdays of the company's schedule, so one axis
        serves everybody; each person's own capacity comes from their schedule.
        """
        calendar = self.env.company.resource_calendar_id
        weekdays = (
            {int(day) for day in calendar.attendance_ids.mapped("dayofweek")}
            if calendar
            else set()
        ) or DEFAULT_WORKING_WEEKDAYS
        days = [today]
        day = today
        while len(days) < DAY_COUNT:
            day -= timedelta(days=1)
            if day.weekday() in weekdays:
                days.append(day)
        return sorted(days)

    def _activity_users(self):
        """The people shown: oneself, or everybody for Project administrators.

        Everybody means the users of Project linked to an employee of the
        current companies, so people who logged nothing show up too, except
        the ones of Settings › Users Left Out of the Reports.
        """
        user = self.env.user
        if not user.has_group("project.group_project_manager"):
            return user
        # sudo: listing the employees of the companies only to know who uses
        # Project; nothing of the employee record itself is shown.
        employees = (
            self.env["hr.employee"]
            .sudo()
            .search(
                [
                    ("user_id", "!=", False),
                    ("company_id", "in", self.env.companies.ids),
                ]
            )
        )
        excluded = self.env["res.users"]._cimalor_report_excluded_users()
        return employees.user_id.filtered(
            lambda person: person.has_group("project.group_project_user")
            and person not in excluded
        )

    @api.model
    def get_activity_data(self):
        """Running timer and recent timesheets of each person, for Team Activity.

        Public (called by the view). Each person sees only themselves and
        Project administrators everybody, as in Workload and Capacity: the
        people are chosen first (_activity_users), then their timers and
        timesheets are read as superuser, because timers are private to their
        user and timesheet rules depend on the Timesheets groups.
        """
        today = fields.Date.context_today(self)
        days = self._activity_days(today)
        users = self._activity_users()
        queue = self.env["cimalor.project.queue"]
        employees = queue._employees_by_user(users)

        # sudo: see the docstring, the users are already restricted.
        Line = self.env["account.analytic.line"].sudo()
        index_of = {day: index for index, day in enumerate(days)}
        # {user id: {project: [hours of each day]}}
        hours = defaultdict(lambda: defaultdict(lambda: [0.0] * len(days)))
        for user, project, day, amount in Line._read_group(
            [
                ("user_id", "in", users.ids),
                ("project_id", "!=", False),
                ("date", ">=", days[0]),
                ("date", "<=", today),
            ],
            groupby=["user_id", "project_id", "date:day"],
            aggregates=["unit_amount:sum"],
        ):
            # Hours of a day off (a weekend) are not on the axis.
            if day in index_of:
                hours[user.id][project][index_of[day]] += amount
        last_entries = dict(
            Line._read_group(
                [("user_id", "in", users.ids), ("project_id", "!=", False)],
                groupby=["user_id"],
                aggregates=["create_date:max"],
            )
        )
        timers = {
            timer.user_id.id: timer
            for timer in self.env["cimalor.project.timer"]
            .sudo()
            .search([("user_id", "in", users.ids)])
        }
        now = fields.Datetime.now()

        people = []
        for user in users.sorted(lambda person: person.name or ""):
            employee = employees.get(user.id)
            capacity = (
                queue._daily_capacity(employee, days[0], today + timedelta(days=1))
                if employee and employee.resource_calendar_id
                else {}
            )
            timer = timers.get(user.id)
            open_project = timer.task_id.project_id if timer else None
            projects = dict(hours[user.id])
            if open_project and open_project not in projects:
                # The project of the running timer has a row, even without hours.
                projects[open_project] = [0.0] * len(days)
            people.append(
                {
                    "user_id": user.id,
                    "name": user.name,
                    "capacity": [round(capacity.get(day, 0.0), 2) for day in days],
                    "timer": (
                        {
                            "project_id": open_project.id,
                            "project": open_project.display_name,
                            "task": timer.task_id.display_name,
                            "elapsed": (now - timer.start).total_seconds() / 3600,
                        }
                        if timer
                        else False
                    ),
                    "last_entry": (
                        fields.Datetime.to_string(last_entries[user])
                        if last_entries.get(user)
                        else False
                    ),
                    **self._activity_rows(projects, open_project),
                }
            )
        form = self.env.ref(
            "cimalor_project_status_board.view_project_project_form",
            raise_if_not_found=False,
        )
        return {
            "days": [
                {"date": fields.Date.to_string(day), "today": day == today}
                for day in days
            ],
            "people": people,
            "project_form_id": form.id if form else False,
        }

    def _activity_rows(self, projects, open_project):
        """At most MAX_PROJECTS project rows, the rest added up as "others".

        The project of the running timer comes first, then the most hours.
        """

        def rank(project):
            return (project != open_project, -sum(projects[project]), project.name)

        ordered = sorted(projects, key=rank)
        shown, rest = ordered[:MAX_PROJECTS], ordered[MAX_PROJECTS:]

        def rounded(values):
            return [round(value, 2) for value in values]

        others = False
        if rest:
            summed = [
                sum(values) for values in zip(*(projects[p] for p in rest), strict=True)
            ]
            others = {"count": len(rest), "hours": rounded(summed)}
        return {
            "rows": [
                {
                    "project_id": project.id,
                    "project": project.display_name,
                    "hours": rounded(projects[project]),
                    "open": project == open_project,
                }
                for project in shown
            ],
            "others": others,
        }
