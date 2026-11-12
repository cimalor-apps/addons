from datetime import date, datetime

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

GROUPS = "project.group_project_user,hr_timesheet.group_hr_timesheet_user"
MONDAY = "2026-11-16"


@tagged("post_install", "-at_install")
class TestCapacityReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env.ref("resource.resource_calendar_std")  # 8 h, Mon-Fri
        cls.user = new_test_user(cls.env, login="psb_cap_user", groups=GROUPS)
        cls.other = new_test_user(cls.env, login="psb_cap_other", groups=GROUPS)
        cls.boss = new_test_user(
            cls.env,
            login="psb_cap_boss",
            groups=GROUPS + ",project.group_project_manager",
        )
        Employee = cls.env["hr.employee"]
        cls.employee = Employee.create(
            {
                "name": "Capacity user",
                "user_id": cls.user.id,
                "resource_calendar_id": cls.calendar.id,
                "tz": "Europe/Madrid",
            }
        )
        Employee.create(
            {
                "name": "Capacity other",
                "user_id": cls.other.id,
                "resource_calendar_id": cls.calendar.id,
            }
        )
        Project = cls.env["project.project"]
        moving = Project.create(
            {
                "name": "Capacity moving",
                "stage_id": cls.env.ref("project.project_project_stage_1").id,
            }
        )
        stopped = Project.create(
            {
                "name": "Capacity on hold",
                "stage_id": cls.env.ref(
                    "cimalor_project_status_board.project_project_stage_on_hold"
                ).id,
            }
        )
        cls.task = cls.env["project.task"].create(
            [
                {
                    "name": "Three days of work",
                    "project_id": moving.id,
                    "allocated_hours": 21,
                    "user_ids": [cls.user.id],
                },
                {
                    "name": "Waits for the restart",
                    "project_id": stopped.id,
                    "allocated_hours": 10,
                    "user_ids": [cls.user.id],
                },
            ]
        )[0]
        cls.Report = cls.env["cimalor.project.capacity.report"]

    def _row(self, user=None):
        # The report reads a database view: write the pending ORM changes first.
        self.env.flush_all()
        return self.Report.with_user(user or self.boss).search(
            [("user_id", "=", self.user.id)]
        )

    @freeze_time(MONDAY)
    def test_capacity_and_queue_end(self):
        """8 h schedule minus 1 h admin: 21 h take Monday to Wednesday."""
        row = self._row()
        self.assertEqual(row.daily_capacity, 7)
        self.assertEqual(row.weekly_capacity, 35)
        self.assertEqual(row.pending_hours, 21)
        self.assertEqual(row.paused_hours, 10, "on hold shown apart")
        self.assertAlmostEqual(row.weeks_of_work, 0.6)
        self.assertEqual(row.queue_end_date, date(2026, 11, 18))

    @freeze_time(MONDAY)
    def test_time_off_moves_the_end(self):
        self.env["resource.calendar.leaves"].create(
            {
                "name": "Day off",
                "calendar_id": self.calendar.id,
                "resource_id": self.employee.resource_id.id,
                "date_from": datetime(2026, 11, 17, 0, 0),
                "date_to": datetime(2026, 11, 17, 22, 0),
            }
        )
        self.assertEqual(self._row().queue_end_date, date(2026, 11, 19))

    @freeze_time(MONDAY)
    def test_hours_logged_today_use_today(self):
        self.env["account.analytic.line"].create(
            {
                "name": "Morning",
                "task_id": self.task.id,
                "project_id": self.task.project_id.id,
                "employee_id": self.employee.id,
                "unit_amount": 5,
            }
        )
        row = self._row()
        # 16 h left; today only 2 h of capacity remain: 2 + 7 + 7 = Wednesday.
        self.assertEqual(row.pending_hours, 16)
        self.assertEqual(row.queue_end_date, date(2026, 11, 18))

    @freeze_time(MONDAY)
    def test_admin_time_per_person(self):
        self.employee.cimalor_admin_hours = 3  # 5 h a day: Monday to Friday
        row = self._row()
        self.assertEqual(row.daily_capacity, 5)
        self.assertEqual(row.queue_end_date, date(2026, 11, 20))

    def test_each_person_sees_their_own_capacity(self):
        self.assertTrue(self._row(self.user))
        self.assertFalse(self._row(self.other), "another person's capacity")
        self.assertTrue(self._row(self.boss))
