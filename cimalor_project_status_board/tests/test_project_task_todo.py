from datetime import date, timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestProjectTaskTodo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Catalogue B2B"})
        cls.task = cls.env["project.task"].create(
            {
                "name": "Seasonal templates",
                "project_id": cls.project.id,
                "allocated_hours": 20,
            }
        )
        cls.subtask = cls.env["project.task"].create(
            {
                "name": "Winter template",
                "project_id": cls.project.id,
                "parent_id": cls.task.id,
            }
        )

    def test_tick_closes_without_touching_estimate(self):
        """Ticking closes the task as done and keeps its planned hours."""
        self.task.cimalor_is_done = True

        self.assertEqual(self.task.state, "1_done")
        self.assertEqual(self.task.allocated_hours, 20)

    def test_untick_reopens(self):
        self.task.state = "1_done"
        self.task.cimalor_is_done = False

        self.assertEqual(self.task.state, "01_in_progress")

    def test_lists_show_main_tasks_only(self):
        """The to-do list shows main tasks; subtasks stay in Project."""
        self.assertEqual(self.project.cimalor_open_task_ids, self.task)

        self.task.cimalor_is_done = True
        self.project.invalidate_recordset(
            ["cimalor_open_task_ids", "cimalor_closed_task_ids"]
        )
        self.assertFalse(self.project.cimalor_open_task_ids)
        self.assertEqual(self.project.cimalor_closed_task_ids, self.task)


@tagged("post_install", "-at_install")
class TestProjectStateSummary(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stage_waiting = cls.env.ref(
            "cimalor_project_status_board.project_project_stage_waiting"
        )
        cls.reason_email = cls.env.ref(
            "cimalor_project_status_board.stop_reason_email_reply"
        )
        cls.project = cls.env["project.project"].create({"name": "E-signature"})

    def test_waiting_summary_and_overdue(self):
        yesterday = fields.Date.context_today(self.project) - timedelta(days=1)
        self.project.write(
            {
                "stage_id": self.stage_waiting.id,
                "cimalor_reason_id": self.reason_email.id,
                "cimalor_follow_up_date": yesterday,
            }
        )

        self.assertIn("Reply to an email", self.project.cimalor_state_summary)
        self.assertTrue(self.project.cimalor_follow_up_overdue)

    def test_missing_data_summary(self):
        self.project.stage_id = self.stage_waiting
        self.assertEqual(
            self.project.cimalor_state_summary,
            "Waiting: reason or follow-up date missing",
        )

    def test_no_summary_in_progress(self):
        """Other states get their sentence with the margins, in 0.4."""
        self.assertFalse(self.project.cimalor_state_summary)
        self.assertFalse(self.project.cimalor_follow_up_overdue)

    def test_since_ignores_edits_within_the_state(self):
        """Changing the date while Waiting does not restart the count."""
        self.project.write(
            {
                "stage_id": self.stage_waiting.id,
                "cimalor_reason_id": self.reason_email.id,
                "cimalor_follow_up_date": date(2026, 11, 2),
            }
        )
        first_waiting = self.project.cimalor_state_log_ids[0]
        self.project.cimalor_follow_up_date = date(2026, 11, 9)

        self.assertEqual(len(self.project.cimalor_state_log_ids), 3)
        self.assertEqual(
            self.project._cimalor_state_since(),
            fields.Datetime.context_timestamp(self.project, first_waiting.date).date(),
        )


@tagged("post_install", "-at_install")
class TestProjectViews(TransactionCase):
    def test_project_app_keeps_its_views(self):
        """The board's views must not replace Project's default ones."""
        views = self.env["project.project"].get_views(
            [(False, "kanban"), (False, "form")]
        )
        ours = {
            self.env.ref("cimalor_project_status_board.view_project_project_kanban").id,
            self.env.ref("cimalor_project_status_board.view_project_project_form").id,
        }
        for view_type in ("kanban", "form"):
            with self.subTest(view_type=view_type):
                self.assertNotIn(views["views"][view_type]["id"], ours)
