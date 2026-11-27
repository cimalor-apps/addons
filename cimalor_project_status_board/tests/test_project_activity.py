from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

GROUPS = "project.group_project_user,hr_timesheet.group_hr_timesheet_user"
TUESDAY = "2026-11-17 12:00:00"


@tagged("post_install", "-at_install")
class TestTeamActivity(TransactionCase):
    """One person, 8 h a day minus 1 h of admin time, seven projects.

    Days on Tuesday 17: Wed 11, Thu 12, Fri 13, Mon 16 and today (the weekend
    is not a working day of the company). P1 to P6 have logged hours; Timed
    has none, but its timer runs since 10:30.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="psb_activity", groups=GROUPS)
        cls.other = new_test_user(cls.env, login="psb_activity_2", groups=GROUPS)
        cls.manager = new_test_user(
            cls.env,
            login="psb_activity_manager",
            groups=GROUPS + ",project.group_project_manager",
        )
        calendar = cls.env.ref("resource.resource_calendar_std")
        cls.env["hr.employee"].create(
            [
                {
                    "name": "Activity user",
                    "user_id": cls.user.id,
                    "resource_calendar_id": calendar.id,
                    "tz": "UTC",
                },
                {"name": "Second user", "user_id": cls.other.id},
            ]
        )
        cls.env.company.resource_calendar_id = calendar
        Project = cls.env["project.project"]
        cls.projects = Project.create([{"name": f"P{n}"} for n in range(1, 7)])
        cls.timed = Project.create({"name": "Timed"})
        cls.timed_task = cls.env["project.task"].create(
            {"name": "Open work", "project_id": cls.timed.id}
        )
        # (project index, date, hours): P1 the most, P6 the least.
        logs = [
            (0, "2026-11-11", 5),
            (0, "2026-11-17", 2),
            (1, "2026-11-12", 4),
            (2, "2026-11-13", 3),
            (2, "2026-11-14", 6),  # Saturday: not on the axis
            (3, "2026-11-16", 2.5),
            (4, "2026-11-16", 1),
            (5, "2026-11-11", 0.5),
            (0, "2026-11-10", 8),  # before the first day
        ]
        cls.env["account.analytic.line"].create(
            [
                {
                    "name": "Work",
                    "project_id": cls.projects[index].id,
                    "user_id": cls.user.id,
                    "date": day,
                    "unit_amount": hours,
                }
                for index, day, hours in logs
            ]
        )

    def _data(self, user):
        return self.env["cimalor.project.activity"].with_user(user).get_activity_data()

    @freeze_time(TUESDAY)
    def test_days_rows_and_timer(self):
        self.env["cimalor.project.timer"].create(
            {
                "user_id": self.user.id,
                "task_id": self.timed_task.id,
                "start": datetime(2026, 11, 17, 10, 30),
            }
        )
        data = self._data(self.user)
        self.assertEqual(
            [day["date"] for day in data["days"]],
            ["2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17"],
        )
        self.assertEqual([day["today"] for day in data["days"]][-1], True)
        self.assertEqual(
            [person["user_id"] for person in data["people"]],
            [self.user.id],
            "a project user sees only themselves",
        )
        person = data["people"][0]
        # The full working day: admin time is logged too, on an internal
        # project, so it is not taken off here (the forecasts still do).
        self.assertEqual(person["capacity"], [8.0] * 5)
        self.assertEqual(person["timer"]["project"], "Timed")
        self.assertAlmostEqual(person["timer"]["elapsed"], 1.5)

        rows = person["rows"]
        self.assertEqual(
            [row["project"] for row in rows],
            ["Timed", "P1", "P2", "P3", "P4"],
            "the running timer's project first, then the most hours, five rows",
        )
        self.assertTrue(rows[0]["open"])
        self.assertEqual(rows[0]["hours"], [0.0] * 5)
        self.assertEqual(rows[1]["hours"], [5.0, 0.0, 0.0, 0.0, 2.0])
        self.assertEqual(
            rows[3]["hours"], [0.0, 0.0, 3.0, 0.0, 0.0], "Saturday left out"
        )
        self.assertEqual(person["others"]["count"], 2, "P5 and P6")
        self.assertEqual(person["others"]["hours"], [0.5, 0.0, 0.0, 1.0, 0.0])

    @freeze_time(TUESDAY)
    def test_without_timer(self):
        person = self._data(self.user)["people"][0]
        self.assertFalse(person["timer"])
        self.assertTrue(person["last_entry"])
        self.assertEqual(
            [row["project"] for row in person["rows"]],
            ["P1", "P2", "P3", "P4", "P5"],
        )
        self.assertEqual(person["others"]["count"], 1)

    @freeze_time(TUESDAY)
    def test_manager_sees_everybody(self):
        outsider = new_test_user(self.env, login="psb_activity_no_project")
        self.env["hr.employee"].create({"name": "No Project", "user_id": outsider.id})
        people = {
            person["user_id"]: person for person in self._data(self.manager)["people"]
        }
        self.assertIn(self.user.id, people)
        self.assertIn(self.other.id, people, "also who logged nothing")
        self.assertEqual(people[self.other.id]["rows"], [])
        self.assertNotIn(
            self.manager.id, people, "without an employee, not in the team"
        )
        self.assertNotIn(outsider.id, people, "not a user of Project")

    def test_weekdays_without_company_schedule(self):
        """Monday to Friday when the company has no working schedule."""
        self.env.company.resource_calendar_id = False
        days = self.env["cimalor.project.activity"]._activity_days(
            datetime(2026, 11, 16).date()
        )
        self.assertEqual(days[0], datetime(2026, 11, 10).date())
        self.assertEqual(len(days), 5)
        self.assertNotIn(datetime(2026, 11, 15).date(), days)
        self.assertEqual(days[-1] - days[0], timedelta(days=6))
