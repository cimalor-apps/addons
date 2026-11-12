from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.cimalor_project_status_board.hooks import (
    _type_native_stages,
    uninstall_hook,
)


@tagged("post_install", "-at_install")
class TestProjectProjectStage(TransactionCase):
    def test_project_stages_enabled(self):
        """Installing the module turns on the Project Stages setting."""
        stages_group = self.env.ref("project.group_project_stages")
        self.assertIn(
            stages_group,
            self.env.ref("base.group_user").implied_ids,
            "every internal user must see project stages, or there are no columns",
        )

    def test_native_stages_typed(self):
        """The four native stages get their state type; Cancelled counts as Done."""
        expected = {
            "project.project_project_stage_0": "to_start",
            "project.project_project_stage_1": "in_progress",
            "project.project_project_stage_2": "done",
            "project.project_project_stage_3": "done",
        }
        for xmlid, state_type in expected.items():
            with self.subTest(stage=xmlid):
                stage = self.env.ref(xmlid)
                self.assertEqual(stage.cimalor_state_type, state_type)

    def test_new_stages(self):
        """Waiting sits right after In Progress; On Hold is folded."""
        waiting = self.env.ref(
            "cimalor_project_status_board.project_project_stage_waiting"
        )
        on_hold = self.env.ref(
            "cimalor_project_status_board.project_project_stage_on_hold"
        )
        in_progress = self.env.ref("project.project_project_stage_1")
        done = self.env.ref("project.project_project_stage_2")

        self.assertEqual(waiting.cimalor_state_type, "waiting")
        self.assertFalse(waiting.fold)
        self.assertEqual(on_hold.cimalor_state_type, "stopped")
        self.assertTrue(on_hold.fold, "On Hold is out of sight until its restart date")
        self.assertLess(in_progress.sequence, waiting.sequence)
        self.assertLess(waiting.sequence, on_hold.sequence)
        self.assertLess(on_hold.sequence, done.sequence)

    def test_uninstall_keeps_stages_in_use(self):
        """A stage with projects survives the uninstall; an empty one does not."""
        waiting = self.env.ref(
            "cimalor_project_status_board.project_project_stage_waiting"
        )
        on_hold = self.env.ref(
            "cimalor_project_status_board.project_project_stage_on_hold"
        )
        self.env["project.project"].search([("stage_id", "=", on_hold.id)]).write(
            {"stage_id": waiting.id}
        )
        self.env["project.project"].create(
            {"name": "Archived but waiting", "stage_id": waiting.id, "active": False}
        )

        uninstall_hook(self.env)

        xmlids = self.env["ir.model.data"].search(
            [
                ("module", "=", "cimalor_project_status_board"),
                ("model", "=", "project.project.stage"),
            ]
        )
        self.assertNotIn(
            waiting.id,
            xmlids.mapped("res_id"),
            "a stage holding projects becomes an ordinary stage, so Odoo keeps it",
        )
        self.assertIn(
            on_hold.id,
            xmlids.mapped("res_id"),
            "an empty stage stays tied to the module and is deleted with it",
        )

    def test_hook_tolerates_deleted_native_stage(self):
        """A customer may have deleted a native stage before installing."""
        cancelled = self.env.ref("project.project_project_stage_3")
        self.env["project.project"].with_context(active_test=False).search(
            [("stage_id", "=", cancelled.id)]
        ).stage_id = self.env.ref("project.project_project_stage_2")
        cancelled.unlink()

        _type_native_stages(self.env)

        self.assertEqual(
            self.env.ref("project.project_project_stage_0").cimalor_state_type,
            "to_start",
        )
