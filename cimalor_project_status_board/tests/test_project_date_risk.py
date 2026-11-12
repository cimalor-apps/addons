from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

GROUPS = "project.group_project_user,hr_timesheet.group_hr_timesheet_user"
MONDAY = "2026-11-16"


@tagged("post_install", "-at_install")
class TestProjectDateRisk(TransactionCase):
    """One person, 7 h a day, three projects in due date order.

    A (due Wed 18, 14 h): Mon-Tue, ends 17 -> +1 day, tight.
    C (due Thu 19, 21 h): Wed-Fri, ends 20 -> -1 day, late.
    B (due Mon 30, 14 h): Mon 23-Tue 24 -> +4 days, on time.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="psb_risk_user", groups=GROUPS)
        cls.env["hr.employee"].create(
            {
                "name": "Risk user",
                "user_id": cls.user.id,
                "resource_calendar_id": cls.env.ref(
                    "resource.resource_calendar_std"
                ).id,
                "tz": "Europe/Madrid",
            }
        )
        in_progress = cls.env.ref("project.project_project_stage_1").id
        on_hold = cls.env.ref(
            "cimalor_project_status_board.project_project_stage_on_hold"
        ).id
        Project = cls.env["project.project"]
        cls.a, cls.b, cls.c, cls.stopped, cls.undated = Project.create(
            [
                {"name": "A", "date": "2026-11-18", "stage_id": in_progress},
                {"name": "B", "date": "2026-11-30", "stage_id": in_progress},
                {"name": "C", "date": "2026-11-19", "stage_id": in_progress},
                {"name": "Held", "date": "2026-11-17", "stage_id": on_hold},
                {"name": "Undated", "stage_id": in_progress},
            ]
        )
        cls.env["project.task"].create(
            [
                {
                    "name": f"Work on {project.name}",
                    "project_id": project.id,
                    "allocated_hours": hours,
                    "user_ids": [cls.user.id],
                }
                for project, hours in (
                    (cls.a, 14),
                    (cls.b, 14),
                    (cls.c, 21),
                    (cls.stopped, 50),
                    (cls.undated, 1),
                )
            ]
        )

    @freeze_time(MONDAY)
    def test_queue_by_due_date(self):
        projects = self.a | self.b | self.c
        projects.invalidate_recordset()
        self.assertEqual(
            projects.mapped("cimalor_forecast_end_date"),
            [date(2026, 11, 17), date(2026, 11, 24), date(2026, 11, 20)],
        )
        self.assertEqual(projects.mapped("cimalor_days_margin"), [1, 4, -1])
        self.assertEqual(
            projects.mapped("cimalor_days_health"), ["tight", "ok", "late"]
        )
        self.assertEqual(self.c.cimalor_late_by, self.user.name)
        self.assertFalse(self.a.cimalor_late_by)

    @freeze_time(MONDAY)
    def test_on_hold_leaves_the_queue(self):
        """50 h on hold are not in front of A, B and C."""
        self.assertFalse(self.stopped.cimalor_days_health)
        self.assertEqual(self.a.cimalor_forecast_end_date, date(2026, 11, 17))

    @freeze_time(MONDAY)
    def test_no_delivery_date_is_grey(self):
        self.assertEqual(self.undated.cimalor_days_health, "no_data")

    @freeze_time(MONDAY)
    def test_filter_late_projects(self):
        Project = self.env["project.project"]
        self.assertEqual(
            Project.search(
                [("cimalor_days_health", "=", "late"), ("id", "in", self.c.ids)]
            ),
            self.c,
        )
        at_risk = Project.search([("cimalor_days_health", "in", ["late", "tight"])])
        self.assertIn(self.a, at_risk)
        self.assertNotIn(self.b, at_risk)

    @freeze_time(MONDAY)
    def test_capacity_shows_the_same_queue_end(self):
        self.env.flush_all()
        row = self.env["cimalor.project.capacity.report"].search(
            [("user_id", "=", self.user.id)]
        )
        # 14 + 21 + 14 + 1 h (the undated task, last) at 7 h a day.
        self.assertEqual(row.queue_end_date, date(2026, 11, 25))


@tagged("post_install", "-at_install")
class TestDeliveryDate(TransactionCase):
    """Project drops a new end date on a project without start date."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create(
            {"name": "Only a delivery date", "date": "2027-01-30"}
        )

    def test_delivery_date_is_saved_without_start_date(self):
        self.assertFalse(self.project.date_start)
        self.project.date = date(2027, 2, 15)

        self.assertEqual(self.project.date, date(2027, 2, 15))
        self.assertEqual(
            self.project.date_start,
            self.project.create_date.date(),
            "start filled in with the creation day",
        )

    def test_start_never_after_delivery(self):
        self.project.date = date(2020, 1, 10)
        self.assertEqual(self.project.date, date(2020, 1, 10))
        self.assertEqual(self.project.date_start, date(2020, 1, 10))

    def test_existing_start_is_kept(self):
        self.project.write({"date_start": "2026-01-01", "date": "2027-01-30"})
        self.project.date = date(2027, 3, 1)
        self.assertEqual(self.project.date_start, date(2026, 1, 1))
        self.assertEqual(self.project.date, date(2027, 3, 1))
