from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

MODULE = "cimalor_project_status_board"
GROUPS = "project.group_project_user,hr_timesheet.group_hr_timesheet_user"


@tagged("post_install", "-at_install")
class TestHourBank(TransactionCase):
    """Settings › Excluded Tasks: hour banks count only their requests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.worker = new_test_user(cls.env, login="psb_bank_worker", groups=GROUPS)
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Bank worker",
                "user_id": cls.worker.id,
                "resource_calendar_id": cls.env.ref(
                    "resource.resource_calendar_std"
                ).id,
            }
        )
        cls.manager = new_test_user(
            cls.env,
            login="psb_bank_manager",
            groups=GROUPS + ",project.group_project_manager",
        )
        cls.in_progress = cls.env.ref("project.project_project_stage_1")
        cls.bank = cls.env["project.project"].create(
            {
                "name": "PSB support bank",
                "user_id": cls.manager.id,
                "stage_id": cls.in_progress.id,
            }
        )
        cls.env["project.task"].create(
            [
                {
                    "name": "[BANK] Billable hours",
                    "project_id": cls.bank.id,
                    "allocated_hours": 100,
                    "user_ids": [cls.worker.id],
                },
                {
                    "name": "[BANK] Non-billable",
                    "project_id": cls.bank.id,
                    "user_ids": [cls.worker.id],
                },
            ]
        )
        cls.idle = cls.env.ref(f"{MODULE}.stop_reason_hour_bank_idle")
        cls.env["res.config.settings"].create(
            {"cimalor_excluded_task_domain": "[('name', 'like', '[BANK]')]"}
        ).execute()

    def _request(self, name="Incident: invoices not sent", hours=5):
        return (
            self.env["project.task"]
            .with_user(self.worker)
            .create(
                {
                    "name": name,
                    "project_id": self.bank.id,
                    "allocated_hours": hours,
                    "user_ids": [self.worker.id],
                }
            )
        )

    def _log(self, task, hours):
        self.env["account.analytic.line"].create(
            {
                "name": "Work",
                "task_id": task.id,
                "project_id": self.bank.id,
                "employee_id": self.employee.id,
                "unit_amount": hours,
            }
        )

    def _notes(self):
        return self.bank.message_ids.filtered(
            lambda m: m.subtype_id == self.env.ref("mail.mt_note")
        ).mapped("body")

    def test_bank_without_requests_goes_on_hold(self):
        self.assertTrue(self.bank.cimalor_is_hour_bank)
        self.assertEqual(self.bank.cimalor_state_type, "stopped")
        self.assertEqual(self.bank.cimalor_reason_id, self.idle)
        self.assertFalse(self.bank.cimalor_missing_state_data, "no date needed")
        self.assertEqual(self.bank.cimalor_state_summary, self.idle.name)
        self.assertTrue(any("automatically" in note for note in self._notes()))
        notices = self.bank.activity_ids.filtered(
            lambda a: a.activity_type_id
            == self.env.ref(f"{MODULE}.mail_activity_type_state_change")
        )
        self.assertFalse(notices, "nobody is told what the module did by itself")

    def test_request_brings_it_back(self):
        request = self._request()

        self.assertEqual(self.bank.cimalor_state_type, "in_progress")
        self.assertTrue(any(request.name in note for note in self._notes()))
        self.assertEqual(self.bank.cimalor_pending_hours, 5, "the balance is not work")
        self.env.flush_all()
        load = self.env["cimalor.project.workload.report"].search(
            [("project_id", "=", self.bank.id)]
        )
        self.assertEqual(load.task_id, request)

    def test_closing_the_last_request_holds_it_again(self):
        request = self._request()
        request.state = "1_done"
        self.assertEqual(self.bank.cimalor_state_type, "stopped")
        self.assertEqual(self.bank.cimalor_reason_id, self.idle)

    def test_margin_is_the_requests_estimate(self):
        request = self._request(hours=5)
        self._log(request, 3)
        self.assertEqual(self.bank.cimalor_hours_margin, 2)
        self.assertEqual(self.bank.cimalor_hours_health, "ok")
        self._log(request, 3)
        self.assertEqual(self.bank.cimalor_hours_margin, -1)
        self.assertEqual(self.bank.cimalor_hours_health, "over")

    def test_bank_on_hold_for_another_reason_is_left_alone(self):
        self.bank.write(
            {
                "cimalor_reason_id": self.env.ref(
                    f"{MODULE}.stop_reason_customer_postpones"
                ).id,
                "cimalor_restart_date": fields.Date.today(),
            }
        )
        self._request()
        self.assertEqual(self.bank.cimalor_state_type, "stopped")

    def test_other_projects_flag_no_open_tasks(self):
        project = self.env["project.project"].create(
            {"name": "PSB normal project", "stage_id": self.in_progress.id}
        )
        self.assertTrue(project.cimalor_no_open_tasks)
        self.env["project.task"].create({"name": "Something", "project_id": project.id})
        self.assertFalse(project.cimalor_no_open_tasks)
        self.assertEqual(project.cimalor_state_type, "in_progress", "never moved")
        self.assertFalse(self.bank.cimalor_no_open_tasks)
