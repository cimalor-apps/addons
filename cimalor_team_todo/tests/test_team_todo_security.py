from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestTeamTodoSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = new_test_user(cls.env, login="tt_alice")
        cls.bob = new_test_user(cls.env, login="tt_bob")
        cls.boss = new_test_user(
            cls.env,
            login="tt_boss",
            groups="base.group_user,cimalor_team_todo.group_team_todo_manager",
        )
        Task = cls.env["team.todo.task"]
        cls.task_alice = Task.create({"name": "Alice task", "user_id": cls.alice.id})
        cls.task_bob = Task.create({"name": "Bob task", "user_id": cls.bob.id})

    def test_every_internal_user_is_a_team_todo_user(self):
        """base.group_user implies the user group, so the app is visible."""
        self.assertTrue(self.alice.has_group("cimalor_team_todo.group_team_todo_user"))

    def test_user_sees_only_their_own_tasks(self):
        visible = self.env["team.todo.task"].with_user(self.alice).search([])
        self.assertIn(self.task_alice, visible)
        self.assertNotIn(
            self.task_bob, visible, "a user must not see other people's tasks"
        )

    def test_manager_sees_every_task(self):
        visible = self.env["team.todo.task"].with_user(self.boss).search([])
        self.assertIn(self.task_alice, visible)
        self.assertIn(self.task_bob, visible)

    def test_reassigning_moves_the_task_from_one_inbox_to_the_other(self):
        """One owner at a time: handing a task over takes it away."""
        self.task_alice.user_id = self.bob

        alice_sees = self.env["team.todo.task"].with_user(self.alice).search([])
        bob_sees = self.env["team.todo.task"].with_user(self.bob).search([])
        self.assertNotIn(self.task_alice, alice_sees)
        self.assertIn(self.task_alice, bob_sees)

    def test_user_cannot_delete_tasks(self):
        """The user ACL grants read/write/create but not unlink."""
        with self.assertRaises(AccessError):
            self.task_alice.with_user(self.alice).unlink()

    def test_manager_can_delete_tasks(self):
        task = self.env["team.todo.task"].create(
            {"name": "Disposable", "user_id": self.alice.id}
        )
        task.with_user(self.boss).unlink()
        self.assertFalse(task.exists())

    def test_user_cannot_write_stages(self):
        """Stages are configuration: read-only for plain users."""
        with self.assertRaises(AccessError):
            self.env.ref("cimalor_team_todo.stage_todo").with_user(self.alice).write(
                {"name": "Hijacked"}
            )

    def test_manager_can_write_stages(self):
        stage = (
            self.env["team.todo.stage"].with_user(self.boss).create({"name": "Extra"})
        )
        self.assertTrue(stage.exists())

    def test_manager_implies_user(self):
        self.assertTrue(self.boss.has_group("cimalor_team_todo.group_team_todo_user"))

    def test_post_init_hook_seeded_the_odoo_admins(self):
        """The hook copies base.group_system members into the manager group."""
        managers = self.env.ref(
            "cimalor_team_todo.group_team_todo_manager"
        ).all_user_ids
        admins = self.env.ref("base.group_system").all_user_ids
        seeded = admins & managers
        self.assertTrue(
            seeded,
            "install must seed the manager group with the Odoo administrators",
        )
