from odoo import fields, models


class TeamTodoTask(models.Model):
    _inherit = "team.todo.task"

    # The base module has no notion of a project: it only makes sense once
    # the Project app is installed, which is exactly when this bridge is.
    project_id = fields.Many2one(
        comodel_name="project.project",
        index=True,
        ondelete="set null",
    )

    def action_open_project_tasks(self):
        """Open the task list of the linked project.

        Called from the project link on the kanban card. The action is not
        built here: project.project already knows how to open its own tasks
        (that is the method behind the 'Tasks' button of the Project app), so
        delegating keeps us on whatever it does in each version.
        """
        self.ensure_one()
        if not self.project_id:
            # The card hides the link when there is no project, but this
            # method is reachable over RPC, so it must not crash.
            return False
        return self.project_id.action_view_tasks()
