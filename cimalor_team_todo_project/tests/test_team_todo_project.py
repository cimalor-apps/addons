from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestTeamTodoProjectBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Bridge project"})
        cls.Task = cls.env["team.todo.task"]
        # team.todo.task requires an assignee, and env.user in tests is the
        # archived __system__ user, so the tasks below need a real one.
        cls.user = new_test_user(cls.env, login="tt_bridge_user")

    def test_project_id_points_to_a_real_odoo_project(self):
        """The bridge is the whole point: project_id is a project.project."""
        field = self.Task._fields["project_id"]
        self.assertEqual(field.comodel_name, "project.project")

    def test_task_can_be_linked_to_a_project(self):
        task = self.Task.create(
            {
                "name": "Task",
                "project_id": self.project.id,
                "user_id": self.user.id,
            }
        )
        self.assertEqual(task.project_id, self.project)

    def test_project_is_optional(self):
        """Team To-Do works without a project; the link is never mandatory."""
        task = self.Task.create({"name": "No project", "user_id": self.user.id})
        self.assertFalse(task.project_id)

    def test_deleting_the_project_clears_the_link(self):
        """ondelete='set null': losing the project must not lose the task."""
        task = self.Task.create(
            {
                "name": "Task",
                "project_id": self.project.id,
                "user_id": self.user.id,
            }
        )
        self.project.unlink()
        self.assertTrue(task.exists(), "the task must survive its project")
        self.assertFalse(task.project_id)

    def test_a_plain_user_can_pick_a_project(self):
        """A Team To-Do user is not necessarily a Project user.

        It still works because the 'project.project on partners' ACL grants
        read access to base.group_user.
        """
        user = new_test_user(self.env, login="tt_no_project_rights")
        self.assertFalse(user.has_group("project.group_project_manager"))
        self.assertTrue(self.env["project.project"].with_user(user).has_access("read"))

    def test_project_link_opens_the_tasks_of_that_project(self):
        """The kanban link delegates to the action of the Project app."""
        task = self.Task.create(
            {
                "name": "Task",
                "project_id": self.project.id,
                "user_id": self.user.id,
            }
        )
        action = task.action_open_project_tasks()
        self.assertEqual(action["res_model"], "project.task")
        self.assertEqual(action["display_name"], self.project.name)
        self.assertEqual(action["context"]["active_id"], self.project.id)
        self.assertEqual(action["context"]["default_project_id"], self.project.id)

    def test_project_link_is_harmless_without_a_project(self):
        """The card hides the link, but RPC can still reach the method."""
        task = self.Task.create({"name": "No project", "user_id": self.user.id})
        self.assertFalse(task.action_open_project_tasks())

    def test_project_link_works_for_a_user_without_project_rights(self):
        """A Team To-Do user is not necessarily a Project user.

        The link must not blow up in their face: reading project.project and
        the action is enough, and both are granted to base.group_user.
        """
        task = self.Task.create(
            {
                "name": "Task",
                "project_id": self.project.id,
                "user_id": self.user.id,
            }
        )
        action = task.with_user(self.user).action_open_project_tasks()
        self.assertEqual(action["res_model"], "project.task")

    def test_tasks_can_be_grouped_by_project(self):
        task = self.Task.create(
            {
                "name": "Task",
                "project_id": self.project.id,
                "user_id": self.user.id,
            }
        )
        groups = self.Task._read_group(
            [("id", "=", task.id)], ["project_id"], ["__count"]
        )
        self.assertEqual(groups[0][0], self.project)
