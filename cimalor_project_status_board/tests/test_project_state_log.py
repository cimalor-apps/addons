from datetime import date

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools.safe_eval import safe_eval

from odoo.addons.cimalor_project_status_board.hooks import uninstall_hook


@tagged("post_install", "-at_install")
class TestProjectStateLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stage_to_start = cls.env.ref("project.project_project_stage_0")
        cls.stage_in_progress = cls.env.ref("project.project_project_stage_1")
        cls.stage_waiting = cls.env.ref(
            "cimalor_project_status_board.project_project_stage_waiting"
        )
        cls.stage_on_hold = cls.env.ref(
            "cimalor_project_status_board.project_project_stage_on_hold"
        )
        cls.reason_email = cls.env.ref(
            "cimalor_project_status_board.stop_reason_email_reply"
        )
        cls.reason_information = cls.env.ref(
            "cimalor_project_status_board.stop_reason_information"
        )
        cls.reason_waiting_other = cls.env.ref(
            "cimalor_project_status_board.stop_reason_waiting_other"
        )
        cls.reason_postpones = cls.env.ref(
            "cimalor_project_status_board.stop_reason_customer_postpones"
        )
        cls.project = cls.env["project.project"].create(
            {"name": "Brochure automation", "stage_id": cls.stage_in_progress.id}
        )

    def test_create_logs_initial_state(self):
        """A new project starts its history with the stage it is created in."""
        log = self.project.cimalor_state_log_ids
        self.assertEqual(len(log), 1)
        self.assertEqual(log.stage_id, self.stage_in_progress)
        self.assertEqual(log.state_type, "in_progress")
        self.assertEqual(log.user_id, self.env.user)

    def test_drag_logs_without_data(self):
        """Dragging the card only sends the stage: the row has no data."""
        self.project.write({"stage_id": self.stage_waiting.id})

        log = self.project.cimalor_state_log_ids[0]
        self.assertEqual(len(self.project.cimalor_state_log_ids), 2)
        self.assertEqual(log.state_type, "waiting")
        self.assertFalse(log.reason_id)
        self.assertTrue(
            self.project.cimalor_missing_state_data,
            "the board must flag a Waiting project without its reason and date",
        )

    def test_form_logs_once_with_data(self):
        """Stage and data saved together give a single row with the data."""
        self.project.write(
            {
                "stage_id": self.stage_waiting.id,
                "cimalor_reason_id": self.reason_email.id,
                "cimalor_follow_up_date": date(2026, 10, 29),
            }
        )

        self.assertEqual(len(self.project.cimalor_state_log_ids), 2)
        log = self.project.cimalor_state_log_ids[0]
        self.assertEqual(log.reason_id, self.reason_email)
        self.assertEqual(log.depends_on, "customer")
        self.assertEqual(log.follow_up_date, date(2026, 10, 29))
        self.assertFalse(self.project.cimalor_missing_state_data)

    def test_waiting_always_depends_on_customer(self):
        """Waiting is never asked who it depends on: it is the customer."""
        self.reason_information.depends_on = "supplier"
        self.project.write(
            {
                "stage_id": self.stage_waiting.id,
                "cimalor_reason_id": self.reason_information.id,
                "cimalor_follow_up_date": date(2026, 10, 29),
            }
        )

        self.assertEqual(self.project.cimalor_depends_on, "customer")
        self.assertEqual(self.project.cimalor_state_log_ids[0].depends_on, "customer")

    def test_on_hold_depends_on_can_be_changed(self):
        """On Hold: the reason proposes who we depend on; the user may correct it."""
        self.project.write(
            {
                "stage_id": self.stage_on_hold.id,
                "cimalor_reason_id": self.reason_postpones.id,
                "cimalor_restart_date": date(2027, 1, 15),
            }
        )
        self.assertEqual(self.project.cimalor_depends_on, "customer", "proposed")
        self.project.cimalor_depends_on = "internal"

        self.assertEqual(self.project.cimalor_depends_on, "internal")
        self.assertEqual(self.project.cimalor_state_log_ids[0].depends_on, "internal")

    def test_leaving_waiting_clears_data(self):
        """The data belongs to the state: leaving it empties the project fields."""
        self.project.write(
            {
                "stage_id": self.stage_waiting.id,
                "cimalor_reason_id": self.reason_email.id,
                "cimalor_follow_up_date": date(2026, 10, 29),
            }
        )
        self.project.stage_id = self.stage_in_progress

        self.assertFalse(self.project.cimalor_reason_id)
        self.assertFalse(self.project.cimalor_depends_on)
        self.assertFalse(self.project.cimalor_follow_up_date)
        self.assertFalse(self.project.cimalor_missing_state_data)
        self.assertEqual(
            self.project.cimalor_state_log_ids[1].reason_id,
            self.reason_email,
            "the history keeps what the state was",
        )

    def test_waiting_reason_dropped_on_hold(self):
        """A Waiting reason does not survive a move to On Hold."""
        self.project.write(
            {
                "stage_id": self.stage_waiting.id,
                "cimalor_reason_id": self.reason_email.id,
                "cimalor_follow_up_date": date(2026, 10, 29),
            }
        )
        self.project.write(
            {
                "stage_id": self.stage_on_hold.id,
                "cimalor_reason_id": self.reason_postpones.id,
                "cimalor_restart_date": date(2027, 1, 15),
            }
        )

        self.assertEqual(self.project.cimalor_reason_id, self.reason_postpones)
        self.assertFalse(self.project.cimalor_follow_up_date)
        self.assertEqual(self.project.cimalor_restart_date, date(2027, 1, 15))

    def test_other_reason_requires_note(self):
        """Other is incomplete until it is explained."""
        self.project.write(
            {
                "stage_id": self.stage_waiting.id,
                "cimalor_reason_id": self.reason_waiting_other.id,
                "cimalor_follow_up_date": date(2026, 10, 29),
            }
        )
        self.assertTrue(self.project.cimalor_missing_state_data)

        self.project.cimalor_state_note = "Signed contract from the notary"
        self.assertFalse(self.project.cimalor_missing_state_data)
        self.assertEqual(
            self.project.cimalor_state_log_ids[0].note,
            "Signed contract from the notary",
        )

    def _new_notes(self, change):
        """Internal notes posted by `change` (creating a project posts one)."""
        note = self.env.ref("mail.mt_note")
        before = self.project.message_ids
        change()
        return (self.project.message_ids - before).filtered(
            lambda message: message.subtype_id == note
        )

    def test_chatter_note_with_state_data(self):
        """Entering Waiting with its data tells the chatter why."""
        notes = self._new_notes(
            lambda: self.project.write(
                {
                    "stage_id": self.stage_waiting.id,
                    "cimalor_reason_id": self.reason_email.id,
                    "cimalor_follow_up_date": date(2026, 10, 29),
                }
            )
        )
        self.assertEqual(len(notes), 1)
        self.assertIn("Reply to an email", notes.body)
        self.assertNotIn("Depends on", notes.body, "Waiting is always the customer")

    def test_chatter_note_on_hold_says_who(self):
        """On Hold does say who the project depends on."""
        notes = self._new_notes(
            lambda: self.project.write(
                {
                    "stage_id": self.stage_on_hold.id,
                    "cimalor_reason_id": self.reason_postpones.id,
                    "cimalor_restart_date": date(2027, 1, 15),
                }
            )
        )
        self.assertIn("Depends on: Customer", notes.body)

    def test_chatter_note_after_drag(self):
        """A drag leaves a note saying the data is still missing."""
        notes = self._new_notes(
            lambda: self.project.write({"stage_id": self.stage_waiting.id})
        )
        self.assertEqual(len(notes), 1)
        self.assertIn("missing", notes.body)

    def test_no_chatter_note_for_plain_moves(self):
        """Project already tracks plain stage changes; no extra note."""
        notes = self._new_notes(
            lambda: self.project.write({"stage_id": self.stage_to_start.id})
        )
        self.assertFalse(notes)

    def test_previous_stage(self):
        """Each row knows where the project came from, for the report."""
        self.project.write({"stage_id": self.stage_waiting.id})
        latest = self.project.cimalor_state_log_ids[0]
        self.assertEqual(latest.previous_stage_id, self.stage_in_progress)
        first = self.project.cimalor_state_log_ids[-1]
        self.assertFalse(first.previous_stage_id, "the first row has no origin")

    def test_no_log_when_nothing_changes(self):
        """Saving the same state again does not add history."""
        self.project.write({"stage_id": self.stage_in_progress.id, "name": "Renamed"})
        self.assertEqual(len(self.project.cimalor_state_log_ids), 1)


@tagged("post_install", "-at_install")
class TestProjectStateSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stage_waiting = cls.env.ref(
            "cimalor_project_status_board.project_project_stage_waiting"
        )
        cls.stage_in_progress = cls.env.ref("project.project_project_stage_1")
        cls.user = new_test_user(
            cls.env, login="psb_user", groups="project.group_project_user"
        )
        cls.manager = new_test_user(
            cls.env, login="psb_manager", groups="project.group_project_user"
        )
        cls.outsider = new_test_user(
            cls.env, login="psb_outsider", groups="project.group_project_user"
        )
        cls.project = cls.env["project.project"].create(
            {"name": "Catalogue", "user_id": cls.manager.id}
        )
        cls.task = cls.env["project.task"].create(
            {
                "name": "Layout",
                "project_id": cls.project.id,
                "user_ids": [Command.set([cls.user.id])],
            }
        )
        cls.notice_type = cls.env.ref(
            "cimalor_project_status_board.mail_activity_type_state_change"
        )

    def _notices(self):
        return self.project.activity_ids.filtered(
            lambda activity: activity.activity_type_id == self.notice_type
        )

    def test_project_user_changes_state(self):
        """Somebody with a task in the project, not only an admin, can move it."""
        project = self.project.with_user(self.user)
        project.stage_id = self.stage_waiting

        log = project.cimalor_state_log_ids[0]
        self.assertEqual(log.state_type, "waiting")
        self.assertEqual(log.user_id, self.user)

    def test_task_closed_still_counts(self):
        """Finishing your task does not take the project away from you."""
        self.task.state = "1_done"
        self.project.with_user(self.user).stage_id = self.stage_waiting
        self.assertEqual(self.project.stage_id, self.stage_waiting)

    def test_outsider_cannot_change_state(self):
        """A Project user without tasks in the project sees it but cannot move it."""
        project = self.project.with_user(self.outsider)
        self.assertEqual(project.name, "Catalogue", "reading is Project's business")
        with self.assertRaises(AccessError):
            project.stage_id = self.stage_waiting

    def test_manager_is_told(self):
        """A change by somebody else leaves the manager one notice, refreshed."""
        self.project.with_user(self.user).stage_id = self.stage_waiting
        notice = self._notices()
        self.assertEqual(len(notice), 1)
        self.assertEqual(notice.user_id, self.manager)
        self.assertIn(self.user.name, notice.summary)

        self.project.with_user(self.user).stage_id = self.stage_in_progress
        self.assertEqual(len(self._notices()), 1, "refreshed, not piled up")

    def test_manager_own_change_is_silent(self):
        self.project.with_user(self.manager).stage_id = self.stage_waiting
        self.assertFalse(self._notices())

    def test_my_projects(self):
        """My Projects: the ones I manage or have tasks in."""
        action = self.env.ref("cimalor_project_status_board.action_project_project_my")
        Project = self.env["project.project"]
        for user, expected in (
            (self.user, True),
            (self.manager, True),
            (self.outsider, False),
        ):
            with self.subTest(user=user.login):
                domain = safe_eval(action.domain, {"uid": user.id})
                found = Project.with_user(user).search(domain)
                self.assertEqual(self.project in found, expected)

    def test_history_follows_project_visibility(self):
        """A private project's changes stay hidden from those who cannot open it."""
        private = self.env["project.project"].create(
            {"name": "Private", "privacy_visibility": "followers"}
        )
        Log = self.env["cimalor.project.state.log"]
        domain = [("project_id", "=", private.id)]
        self.assertFalse(Log.with_user(self.outsider).search(domain))

        private.message_subscribe(partner_ids=self.outsider.partner_id.ids)
        self.assertTrue(Log.with_user(self.outsider).search(domain), "once invited")

        admin = new_test_user(
            self.env, login="psb_admin", groups="project.group_project_manager"
        )
        private.message_unsubscribe(partner_ids=self.outsider.partner_id.ids)
        self.assertTrue(Log.with_user(admin).search(domain), "administrators see all")

    def test_latest_changes_report_loads(self):
        action = self.env.ref(
            "cimalor_project_status_board.action_cimalor_project_state_log_report"
        )
        views = (
            self.env["cimalor.project.state.log"]
            .with_user(self.user)
            .get_views(
                [(action.view_id.id, "list"), (action.search_view_id.id, "search")]
            )
        )
        self.assertIn("previous_stage_id", views["views"]["list"]["arch"])

    def test_uninstall_moves_notices_to_todo(self):
        """Uninstalling must not fail on the module's activity type (18.0)."""
        self.project.with_user(self.user).stage_id = self.stage_waiting
        notice = self._notices()
        uninstall_hook(self.env)
        self.assertEqual(
            notice.activity_type_id, self.env.ref("mail.mail_activity_data_todo")
        )

    def test_history_is_read_only(self):
        """The history is never rewritten, not even by the person who made it."""
        log = self.project.with_user(self.user).cimalor_state_log_ids[0]
        with self.assertRaises(AccessError):
            log.note = "Rewritten"
        with self.assertRaises(AccessError):
            log.unlink()

    def test_project_user_cannot_manage_reasons(self):
        """Reasons are configuration: only Project administrators edit them."""
        with self.assertRaises(AccessError):
            self.env["cimalor.project.stop.reason"].with_user(self.user).create(
                {"name": "Holidays", "reason_type": "stopped", "depends_on": "internal"}
            )
