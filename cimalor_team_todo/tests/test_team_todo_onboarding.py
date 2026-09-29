from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from ..hooks import post_init_hook


@tagged("post_install", "-at_install")
class TestTeamTodoOnboarding(TransactionCase):
    def _welcome_tasks(self, user):
        return self.env["team.todo.task"].search(
            [("user_id", "=", user.id), ("name", "ilike", "Welcome to Team To-Do")]
        )

    def test_install_gave_every_administrator_one_welcome_task(self):
        """The hook already ran at install for the Odoo administrators."""
        admins = self.env.ref("base.group_system").all_user_ids.filtered(
            lambda u: u.active and not u.share
        )
        self.assertTrue(admins, "a fresh database always has an administrator")
        for admin in admins:
            self.assertEqual(len(self._welcome_tasks(admin)), 1, admin.login)

    def test_hook_targets_administrators_only(self):
        """Plain users must not find a task that nobody on the team assigned."""
        boss = new_test_user(
            self.env,
            login="tt_welcome_boss",
            groups="base.group_user,base.group_system",
        )
        plain = new_test_user(self.env, login="tt_welcome_plain")

        post_init_hook(self.env)

        self.assertEqual(len(self._welcome_tasks(boss)), 1)
        self.assertFalse(self._welcome_tasks(plain))

    def test_welcome_task_is_rendered_for_its_owner(self):
        """The body comes from the QWeb template, addressed to the user."""
        boss = new_test_user(
            self.env,
            login="tt_welcome_render",
            groups="base.group_user,base.group_system",
        )
        post_init_hook(self.env)
        task = self._welcome_tasks(boss)
        self.assertIn(boss.name, task.description)
        self.assertIn("Done", task.description)
        self.assertEqual(task.stage_id, self.env.ref("cimalor_team_todo.stage_todo"))

    def test_welcome_task_sends_no_notification(self):
        """Installing an app must not email anybody about an assignment."""
        boss = new_test_user(
            self.env,
            login="tt_welcome_quiet",
            groups="base.group_user,base.group_system",
        )
        post_init_hook(self.env)
        task = self._welcome_tasks(boss)
        self.assertFalse(task.message_ids.notification_ids)
