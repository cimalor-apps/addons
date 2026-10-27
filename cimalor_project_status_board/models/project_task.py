from odoo import api, fields, models

from odoo.addons.project.models.project_task import CLOSED_STATES


class ProjectTask(models.Model):
    _inherit = "project.task"

    # The checkbox of the to-do list on the project form. It is only a view
    # of the native `state`, so tasks closed from Project, the timer or an
    # import show up ticked too. Closing goes through the state and never
    # through the stage, because stages are configured per project.
    cimalor_is_done = fields.Boolean(
        string="Done",
        compute="_compute_cimalor_is_done",
        inverse="_inverse_cimalor_is_done",
    )

    @api.depends("state")
    def _compute_cimalor_is_done(self):
        for task in self:
            task.cimalor_is_done = task.state in CLOSED_STATES

    def _inverse_cimalor_is_done(self):
        """Ticking closes the task as done; unticking reopens it.

        `allocated_hours` is never touched: the original estimate is what
        later improves the quotes.
        """
        for task in self:
            if task.cimalor_is_done and task.state not in CLOSED_STATES:
                task.state = "1_done"
            elif not task.cimalor_is_done and task.state in CLOSED_STATES:
                task.state = "01_in_progress"
