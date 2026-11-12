from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

GROUPS = "project.group_project_user,hr_timesheet.group_hr_timesheet_user"


@tagged("post_install", "-at_install")
class TestProjectTimer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="psb_timer", groups=GROUPS)
        cls.env["hr.employee"].create({"name": "Timer user", "user_id": cls.user.id})
        cls.other = new_test_user(cls.env, login="psb_timer_other", groups=GROUPS)
        cls.env["hr.employee"].create({"name": "Other user", "user_id": cls.other.id})
        cls.project = cls.env["project.project"].create({"name": "Timed project"})
        cls.task_a, cls.task_b = cls.env["project.task"].create(
            [
                {"name": "Layout", "project_id": cls.project.id},
                {"name": "Templates", "project_id": cls.project.id},
            ]
        )
        cls.Timer = cls.env["cimalor.project.timer"]
        cls.Line = cls.env["account.analytic.line"]

    def _backdate(self, minutes):
        """Pretend the running timer started `minutes` ago."""
        self.Timer.search([("user_id", "=", self.user.id)]).write(
            {"start": fields.Datetime.now() - timedelta(minutes=minutes)}
        )

    def test_start_shows_for_the_user_only(self):
        self.task_a.with_user(self.user).action_cimalor_timer_start()

        self.assertTrue(self.task_a.with_user(self.user).cimalor_timer_start)
        self.assertFalse(
            self.task_a.with_user(self.other).cimalor_timer_start,
            "a running timer is personal",
        )

    def _dialog(self, action, description):
        """Open the stop dialog returned by `action` as the timer user."""
        return (
            self.env[action["res_model"]]
            .with_user(self.user)
            .with_context(**action["context"])
            .create({"description": description})
        )

    def test_stop_logs_time_with_description(self):
        task = self.task_a.with_user(self.user)
        task.action_cimalor_timer_start()
        self._backdate(90)

        wizard = self._dialog(task.action_cimalor_timer_stop(), "First draft")
        self.assertAlmostEqual(wizard.hours, 1.5, places=2)
        wizard.action_confirm()

        line = self.Line.search([("task_id", "=", self.task_a.id)])
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.unit_amount, 1.5, places=2)
        self.assertEqual(line.name, "First draft")
        self.assertEqual(line.user_id, self.user)
        self.assertFalse(task.cimalor_timer_start, "the timer stops once logged")

    def test_one_timer_per_user(self):
        """Play on a second task asks for the first one's comment, then switches."""
        self.task_a.with_user(self.user).action_cimalor_timer_start()
        self._backdate(30)
        action = self.task_b.with_user(self.user).action_cimalor_timer_start()

        self.assertEqual(action["res_model"], "cimalor.project.timer.stop")
        running = self.Timer.search([("user_id", "=", self.user.id)])
        self.assertEqual(running.task_id, self.task_a, "nothing changes until logged")

        self._dialog(action, "Layout finished").action_confirm()

        running = self.Timer.search([("user_id", "=", self.user.id)])
        self.assertEqual(running.task_id, self.task_b)
        line = self.Line.search([("task_id", "=", self.task_a.id)])
        self.assertAlmostEqual(line.unit_amount, 0.5, places=2)
        self.assertEqual(line.name, "Layout finished")

    def test_comment_is_required(self):
        """A comment of spaces is no comment."""
        task = self.task_a.with_user(self.user)
        task.action_cimalor_timer_start()
        self._backdate(30)
        wizard = self._dialog(task.action_cimalor_timer_stop(), "   ")
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertTrue(task.cimalor_timer_start, "still running")

    def test_under_a_minute_logs_nothing(self):
        """A misclick on play then stop does not leave a zero-hour line."""
        task = self.task_a.with_user(self.user)
        task.action_cimalor_timer_start()
        self._dialog(task.action_cimalor_timer_stop(), "Oops").action_confirm()

        self.assertFalse(task.cimalor_timer_start)
        self.assertFalse(self.Line.search([("task_id", "=", self.task_a.id)]))

    def test_last_comment_on_the_project(self):
        """The card shows the latest timesheet comment, to everyone."""
        task = self.task_a.with_user(self.user)
        task.action_cimalor_timer_start()
        self._backdate(30)
        self._dialog(
            task.action_cimalor_timer_stop(), "Sent to the customer"
        ).action_confirm()

        project = self.project.with_user(self.other)
        self.assertEqual(project.cimalor_last_comment, "Sent to the customer")
        self.assertEqual(project.cimalor_last_comment_user_id, self.user)

        # A line without description (from Timesheets, say) does not hide it.
        self.Line.create(
            {
                "project_id": self.project.id,
                "task_id": self.task_b.id,
                "unit_amount": 1,
                "user_id": self.other.id,
            }
        )
        self.assertEqual(self.project.cimalor_last_comment, "Sent to the customer")

    def test_cancelling_the_dialog_keeps_it_running(self):
        task = self.task_a.with_user(self.user)
        task.action_cimalor_timer_start()
        task.action_cimalor_timer_stop()  # the dialog is closed without confirming

        self.assertTrue(task.cimalor_timer_start)
        self.assertFalse(self.Line.search([("task_id", "=", self.task_a.id)]))

    def test_no_employee_no_timer(self):
        """Without an employee the time could not be logged: refuse at start."""
        lonely = new_test_user(self.env, login="psb_no_employee", groups=GROUPS)
        with self.assertRaises(UserError):
            self.task_a.with_user(lonely).action_cimalor_timer_start()

    def test_timers_are_private(self):
        self.task_a.with_user(self.user).action_cimalor_timer_start()
        self.assertFalse(self.Timer.with_user(self.other).search([]))
