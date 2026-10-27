from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


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
        self.assertEqual(log.depends_on, "customer", "proposed by the reason")
        self.assertEqual(log.follow_up_date, date(2026, 10, 29))
        self.assertFalse(self.project.cimalor_missing_state_data)

    def test_depends_on_can_be_changed(self):
        """The reason proposes who we depend on; the user may correct it."""
        self.project.write(
            {
                "stage_id": self.stage_waiting.id,
                "cimalor_reason_id": self.reason_information.id,
                "cimalor_follow_up_date": date(2026, 10, 29),
            }
        )
        self.project.cimalor_depends_on = "supplier"

        self.assertEqual(self.project.cimalor_depends_on, "supplier")
        self.assertEqual(self.project.cimalor_state_log_ids[0].depends_on, "supplier")

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

    def test_no_log_when_nothing_changes(self):
        """Saving the same state again does not add history."""
        self.project.write({"stage_id": self.stage_in_progress.id, "name": "Renamed"})
        self.assertEqual(len(self.project.cimalor_state_log_ids), 1)


@tagged("post_install", "-at_install")
class TestProjectStateSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Catalogue"})
        cls.stage_waiting = cls.env.ref(
            "cimalor_project_status_board.project_project_stage_waiting"
        )
        cls.user = new_test_user(
            cls.env, login="psb_user", groups="project.group_project_user"
        )

    def test_project_user_changes_state(self):
        """A Project user, not only an administrator, can move a project."""
        project = self.project.with_user(self.user)
        project.stage_id = self.stage_waiting

        log = project.cimalor_state_log_ids[0]
        self.assertEqual(log.state_type, "waiting")
        self.assertEqual(log.user_id, self.user)

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
