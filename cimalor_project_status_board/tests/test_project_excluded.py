from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools.safe_eval import safe_eval

MODULE = "cimalor_project_status_board"
GROUPS = "project.group_project_user,hr_timesheet.group_hr_timesheet_user"


@tagged("post_install", "-at_install")
class TestExcludedProjects(TransactionCase):
    """Settings › Excluded Projects: hour banks and the like leave the board."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="psb_excl_user", groups=GROUPS)
        cls.env["hr.employee"].create(
            {
                "name": "Exclusion user",
                "user_id": cls.user.id,
                "resource_calendar_id": cls.env.ref(
                    "resource.resource_calendar_std"
                ).id,
            }
        )
        stage = cls.env.ref("project.project_project_stage_1")
        cls.bank, cls.normal = cls.env["project.project"].create(
            [
                {"name": "PSB hour bank", "stage_id": stage.id},
                {"name": "PSB normal project", "stage_id": stage.id},
            ]
        )
        cls.env["project.task"].create(
            [
                {
                    "name": f"Work in {project.name}",
                    "project_id": project.id,
                    "allocated_hours": 10,
                    "user_ids": [cls.user.id],
                }
                for project in (cls.bank, cls.normal)
            ]
        )

    def _set_filter(self, domain):
        self.env["res.config.settings"].create(
            {"cimalor_excluded_project_domain": domain}
        ).execute()

    def _board(self, xmlid):
        action = self.env.ref(f"{MODULE}.{xmlid}")
        domain = safe_eval(action.domain, {"uid": self.env.uid})
        return self.env["project.project"].search(domain)

    def test_nothing_excluded_by_default(self):
        self.assertFalse(self.bank.cimalor_excluded)
        self.assertIn(self.bank, self._board("action_project_project"))

    def test_filter_leaves_projects_out_everywhere(self):
        self._set_filter("[('name', 'ilike', 'hour bank')]")

        self.assertTrue(self.bank.cimalor_excluded)
        self.assertFalse(self.normal.cimalor_excluded)
        self.assertNotIn(self.bank, self._board("action_project_project"))
        self.assertNotIn(self.bank, self._board("action_project_project_date_risk"))
        self.assertIn(self.normal, self._board("action_project_project"))

        self.env.flush_all()
        load = self.env["cimalor.project.workload.report"].search(
            [("user_id", "=", self.user.id)]
        )
        self.assertEqual(load.project_id, self.normal, "no hours from the bank")
        capacity = self.env["cimalor.project.capacity.report"].search(
            [("user_id", "=", self.user.id)]
        )
        self.assertEqual(capacity.pending_hours, 10)

    def test_projects_follow_their_own_changes(self):
        self._set_filter("[('name', 'ilike', 'hour bank')]")

        self.normal.name = "PSB second hour bank"
        self.assertTrue(self.normal.cimalor_excluded, "renamed into the filter")
        self.bank.name = "PSB ordinary project"
        self.assertFalse(self.bank.cimalor_excluded, "renamed out of it")

        new = self.env["project.project"].create({"name": "PSB third hour bank"})
        self.assertTrue(new.cimalor_excluded, "new projects too")

    def test_clearing_the_filter_brings_them_back(self):
        self._set_filter("[('name', 'ilike', 'hour bank')]")
        self._set_filter(False)
        self.assertFalse(self.bank.cimalor_excluded)

    def test_daily_refresh(self):
        """The daily job catches projects that changed without a write.

        The job is checked to call the refresh, and the refresh is run
        directly: Odoo's scheduler runs jobs with its own locking and
        transaction handling, which is not what this test is about.
        """
        cron = self.env.ref(f"{MODULE}.ir_cron_refresh_excluded_projects")
        self.assertEqual(cron.code.strip(), "model._cimalor_refresh_excluded()")
        self.env["ir.config_parameter"].set_param(
            f"{MODULE}.excluded_project_domain", "[('name', 'ilike', 'hour bank')]"
        )
        self.assertFalse(self.bank.cimalor_excluded)
        self.env["project.project"]._cimalor_refresh_excluded()
        self.assertTrue(self.bank.cimalor_excluded)

    def test_invalid_filter_is_refused(self):
        with self.assertRaises(UserError):
            self._set_filter("[('no_such_field', '=', 1)]")
