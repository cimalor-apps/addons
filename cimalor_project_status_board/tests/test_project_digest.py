import re
from datetime import datetime

from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

MODULE = "cimalor_project_status_board"
GROUPS = "project.group_project_user,hr_timesheet.group_hr_timesheet_user"
MANAGER_GROUPS = GROUPS + ",project.group_project_manager"
MONDAY = "2026-11-16 12:00:00"


class PeopleCase(TransactionCase):
    """A worker and their boss, both with tasks; an administrator looks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.worker = new_test_user(
            cls.env,
            login="psb_digest_worker",
            name="Worker",
            groups=GROUPS,
            email="w@example.com",
        )
        cls.boss = new_test_user(
            cls.env,
            login="psb_digest_boss",
            name="Boss",
            groups=GROUPS,
            email="b@example.com",
        )
        cls.admin = new_test_user(
            cls.env,
            login="psb_digest_admin",
            name="Admin",
            groups=MANAGER_GROUPS,
            email="a@example.com",
        )
        calendar = cls.env.ref("resource.resource_calendar_std")
        cls.env.company.resource_calendar_id = calendar
        cls.env["hr.employee"].create(
            [
                {
                    "name": name,
                    "user_id": user.id,
                    "resource_calendar_id": calendar.id,
                    "tz": "UTC",
                }
                for name, user in (
                    ("Worker", cls.worker),
                    ("Boss", cls.boss),
                    ("Admin", cls.admin),
                )
            ]
        )
        in_progress = cls.env.ref("project.project_project_stage_1").id
        cls.project = cls.env["project.project"].create(
            {
                "name": "Overrun",
                "allocated_hours": 5,
                "date": "2026-11-30",
                "user_id": cls.boss.id,
                "stage_id": in_progress,
            }
        )
        cls.env["project.task"].create(
            [
                {
                    "name": f"Work of {user.name}",
                    "project_id": cls.project.id,
                    "allocated_hours": 10,
                    "user_ids": [user.id],
                }
                for user in (cls.worker, cls.boss)
            ]
        )
        cls.env["account.analytic.line"].create(
            {
                "name": "Analysis",
                "project_id": cls.project.id,
                "user_id": cls.worker.id,
                "date": "2026-11-16",
                "unit_amount": 3,
            }
        )

    def _leave_out(self, *users):
        self.env["res.config.settings"].create(
            {
                "cimalor_excluded_employee_ids": [
                    Command.set([user.employee_id.id for user in users])
                ]
            }
        ).execute()


@tagged("post_install", "-at_install")
class TestExcludedUsers(PeopleCase):
    def test_setting_lives_on_the_company(self):
        self._leave_out(self.boss)
        self.assertEqual(
            self.env.company.cimalor_excluded_employee_ids, self.boss.employee_id
        )
        self.assertEqual(
            self.env["res.users"]
            .with_user(self.admin)
            ._cimalor_report_excluded_users(),
            self.boss,
            "read by a Project administrator without HR rights",
        )

    @freeze_time(MONDAY)
    def test_team_activity(self):
        def people(user):
            data = self.env["cimalor.project.activity"].with_user(user)
            return {person["user_id"] for person in data.get_activity_data()["people"]}

        self.assertIn(self.boss.id, people(self.admin))
        self._leave_out(self.boss, self.admin)
        team = people(self.admin)
        self.assertIn(self.worker.id, team)
        self.assertNotIn(self.boss.id, team)
        self.assertNotIn(self.admin.id, team, "out of the team view, self too")
        self.assertEqual(
            people(self.boss), {self.boss.id}, "who sees only themselves still does"
        )

    def test_workload_and_capacity(self):
        domain = [("user_excluded", "=", False)]
        for model in (
            "cimalor.project.workload.report",
            "cimalor.project.capacity.report",
        ):
            Report = self.env[model].with_user(self.admin)
            self.assertIn(self.boss, Report.search(domain).user_id)
            self._leave_out(self.boss)
            self.assertNotIn(self.boss, Report.search(domain).user_id, model)
            self.assertIn(self.worker, Report.search(domain).user_id, model)
            self.assertEqual(
                Report.search([("user_excluded", "=", True)]).user_id, self.boss
            )
            self._leave_out()
        self._leave_out(self.boss)
        own = self.env["cimalor.project.workload.report"].with_user(self.boss)
        self.assertEqual(own.search(domain).user_id, self.boss)

    def test_action_domains(self):
        for xml_id in (
            "action_cimalor_project_workload_report",
            "action_cimalor_project_capacity_report",
        ):
            action = self.env.ref(f"{MODULE}.{xml_id}")
            self.assertIn("user_excluded", action.domain)

    @freeze_time(MONDAY)
    def test_queue_by_person(self):
        self._leave_out(self.boss)
        data = self.env["cimalor.project.queue"].with_user(self.admin)
        names = [person["name"] for person in data.get_timeline_data()["people"]]
        self.assertIn(self.worker.name, names)
        self.assertNotIn(self.boss.name, names)

    def test_project_figures_unchanged(self):
        """The boss's task still counts: the margins do not lie."""
        pending = self.project.cimalor_pending_hours
        self._leave_out(self.boss)
        self.project.invalidate_recordset()
        self.assertEqual(self.project.cimalor_pending_hours, pending)
        self.assertEqual(pending, 20)


@tagged("post_install", "-at_install")
class TestDailyEmail(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.waiting = cls.env["project.project"].create(
            {"name": "Silent customer", "user_id": cls.admin.id}
        )
        cls.waiting.write(
            {
                "stage_id": cls.env.ref(f"{MODULE}.project_project_stage_waiting").id,
                "cimalor_reason_id": cls.env.ref(
                    f"{MODULE}.stop_reason_email_reply"
                ).id,
                "cimalor_follow_up_date": "2026-11-12",
            }
        )

    def _mails(self):
        return self.env["mail.mail"].search(
            [("subject", "like", "Project Status Board")]
        )

    def _send(self, *recipients):
        self.env.company.cimalor_digest_user_ids = [
            Command.set([user.id for user in recipients])
        ]
        before = self._mails()
        self.env["cimalor.project.digest"]._cron_send_daily_email()
        return self._mails() - before

    @freeze_time(MONDAY)
    def test_nobody_on_the_list(self):
        self.assertFalse(self._send())

    @freeze_time(MONDAY)
    def test_email_content(self):
        self.env["cimalor.project.timer"].create(
            {
                "user_id": self.worker.id,
                "task_id": self.project.task_ids[0].id,
                "start": datetime(2026, 11, 16, 11, 30),
            }
        )
        mail = self._send(self.admin)
        self.assertEqual(len(mail), 1)
        self.assertEqual(mail.email_to, self.admin.email_formatted)
        body = mail.body_html
        for text in (
            "Team Activity",
            "Worker",
            "Boss",
            "Overrun",  # at risk: 5 h allocated - 3 h spent - 20 h pending
            "18 h over",
            "Silent customer",  # follow-up overdue since the 12th
            "4 days ago",
            "1 at risk",
            "1 follow-up overdue",
            "Timer running when this email was sent",
            "3.5 h",  # 3 h logged today + 30 min of the running timer
        ):
            self.assertIn(text, body)

    def _cards(self, mail):
        """Names on the people's cards (managers also appear in the tables)."""
        return set(
            re.findall(r'font-size: 15px; font-weight: bold;">([^<]*)<', mail.body_html)
        )

    @freeze_time(MONDAY)
    def test_excluded_people_are_not_in_it(self):
        self._leave_out(self.boss)
        cards = self._cards(self._send(self.admin))
        self.assertIn("Worker", cards)
        self.assertNotIn("Boss", cards)

    @freeze_time(MONDAY)
    def test_each_recipient_sees_their_own(self):
        mails = self._send(self.admin, self.worker)
        self.assertEqual(len(mails), 2)
        worker_mail = mails.filtered(
            lambda m: m.email_to == self.worker.email_formatted
        )
        self.assertEqual(self._cards(worker_mail), {"Worker"})
        admin_mail = mails - worker_mail
        self.assertTrue({"Worker", "Boss"} <= self._cards(admin_mail))

    @freeze_time(MONDAY)
    def test_recipient_without_email_is_skipped(self):
        self.worker.email = False
        self.assertEqual(len(self._send(self.admin, self.worker)), 1)

    @freeze_time(MONDAY)
    def test_forgotten_timer_says_since_when(self):
        """A timer from another day: since when, not a long duration."""
        self.env["cimalor.project.timer"].create(
            {
                "user_id": self.worker.id,
                "task_id": self.project.task_ids[0].id,
                "start": datetime(2026, 11, 13, 9, 15),
            }
        )
        body = self._send(self.admin).body_html
        self.assertIn("Timer running since 13 Nov at 09:15", body)

    def test_next_send_moves_the_job(self):
        cron = self.env.ref(f"{MODULE}.ir_cron_cimalor_project_digest")
        when = datetime(2026, 12, 1, 18, 0)
        self.env["res.config.settings"].create(
            {"cimalor_digest_next_send": when}
        ).execute()
        self.assertEqual(cron.nextcall, when)
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.cimalor_digest_next_send, when)
