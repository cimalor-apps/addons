from psycopg2.errors import NotNullViolation

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestTeamTodoTask(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stage_todo = cls.env.ref("cimalor_team_todo.stage_todo")
        cls.stage_progress = cls.env.ref("cimalor_team_todo.stage_in_progress")
        cls.stage_done = cls.env.ref("cimalor_team_todo.stage_done")
        cls.Task = cls.env["team.todo.task"]
        cls.user_a = new_test_user(cls.env, login="tt_task_a")
        cls.user_b = new_test_user(cls.env, login="tt_task_b")

    def test_is_done_follows_stage(self):
        """is_done is a stored related field: it must track the stage."""
        task = self.Task.create({"name": "Task", "stage_id": self.stage_todo.id})
        self.assertFalse(task.is_done)

        task.stage_id = self.stage_done
        self.assertTrue(task.is_done, "moving to a closing stage must set is_done")

        task.stage_id = self.stage_progress
        self.assertFalse(task.is_done, "leaving it must clear is_done again")

    def test_is_done_is_searchable(self):
        """Being stored is the whole point: it has to be usable in a domain."""
        done = self.Task.create({"name": "Done", "stage_id": self.stage_done.id})
        open_task = self.Task.create({"name": "Open", "stage_id": self.stage_todo.id})

        found = self.Task.search(
            [("is_done", "=", True), ("id", "in", (done + open_task).ids)]
        )
        self.assertEqual(found, done)

    def test_is_done_follows_stage_flag_change(self):
        """Flipping the flag on the stage must propagate to its tasks."""
        task = self.Task.create({"name": "Task", "stage_id": self.stage_progress.id})
        self.assertFalse(task.is_done)

        self.stage_progress.is_done = True
        self.assertTrue(task.is_done)

    def test_default_stage_is_the_first_one(self):
        """A new task lands on the lowest-sequence stage."""
        task = self.Task.create({"name": "Task"})
        self.assertEqual(task.stage_id, self.stage_todo)

    def test_default_assignee_is_current_user(self):
        """A new task is assigned to whoever creates it."""
        task = self.Task.with_user(self.user_a).create({"name": "Task"})
        self.assertEqual(task.user_id, self.user_a)

    def test_only_one_assignee_at_a_time(self):
        """Assigning is replacing: the work never belongs to two people."""
        task = self.Task.create({"name": "Task", "user_id": self.user_a.id})
        task.user_id = self.user_b
        self.assertEqual(task.user_id, self.user_b)

    def test_assignee_is_required(self):
        """Every task has an owner: no orphan tasks, no invisible tasks."""
        self.assertTrue(self.Task._fields["user_id"].required)
        # required=True on a Many2one is a NOT NULL column: passing False
        # explicitly skips the default and the database refuses the row.
        with self.assertRaises(NotNullViolation), mute_logger("odoo.sql_db"):
            self.Task.create({"name": "Nobody's task", "user_id": False})

    def test_portal_users_cannot_be_assigned(self):
        """The field domain keeps the work inside the staff."""
        self.assertEqual(self.Task._fields["user_id"].domain, "[('share', '=', False)]")

    def test_tasks_can_be_grouped_by_assignee(self):
        """The 'Tasks by Person' action groups on this field."""
        task = self.Task.create({"name": "Task", "user_id": self.user_a.id})
        groups = self.Task._read_group([("id", "=", task.id)], ["user_id"], ["__count"])
        self.assertEqual(groups[0][0], self.user_a)

    def test_group_expand_returns_every_stage(self):
        """Empty stages must still show up as kanban columns.

        group_expand only fires when the context carries read_group_expand,
        which is what the kanban view sets.
        """
        groups = self.Task.with_context(read_group_expand=True).formatted_read_group(
            [("id", "=", False)], ["stage_id"], ["__count"]
        )
        stage_ids = [row["stage_id"][0] for row in groups if row["stage_id"]]
        self.assertEqual(
            set(stage_ids),
            set(self.env["team.todo.stage"].search([]).ids),
            "group_expand must list all stages even with no matching tasks",
        )

    def test_stage_is_required(self):
        """The model declares stage_id required, and it has a default."""
        self.assertTrue(self.Task._fields["stage_id"].required)
