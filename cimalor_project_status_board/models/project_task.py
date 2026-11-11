from odoo import api, fields, models
from odoo.exceptions import UserError

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

    # When the current user's timer on this task started; empty if it is not
    # running. It depends on who is looking (depends_context uid): each user
    # sees only their own timer. The cimalor_timer widget turns it into a
    # live counter.
    cimalor_timer_start = fields.Datetime(
        string="Timer",
        compute="_compute_cimalor_timer_start",
    )

    @api.depends_context("uid")
    def _compute_cimalor_timer_start(self):
        timers = self.env["cimalor.project.timer"].search(
            [("user_id", "=", self.env.uid), ("task_id", "in", self.ids)]
        )
        start_by_task = {timer.task_id.id: timer.start for timer in timers}
        for task in self:
            task.cimalor_timer_start = start_by_task.get(task.id, False)

    def action_cimalor_timer_start(self):
        """Start the current user's timer on this task.

        One timer per user, as Odoo Enterprise does: a timer already running
        on another task is stopped and its time logged without a description.
        The employee is checked here and not at the stop, so nobody runs a
        timer for an hour and then cannot log it.
        """
        self.ensure_one()
        if not self.env.user.employee_id:
            raise UserError(
                self.env._(
                    "You need an employee in this company to log time. Ask your "
                    "administrator to link your user to an employee."
                )
            )
        Timer = self.env["cimalor.project.timer"]
        running = Timer.search([("user_id", "=", self.env.uid)])
        for timer in running:
            timer._cimalor_log_time(timer._cimalor_elapsed_hours())
        Timer.create({"task_id": self.id})

    def action_cimalor_timer_stop(self):
        """Open the stop dialog to confirm the hours and add a description."""
        self.ensure_one()
        timer = self.env["cimalor.project.timer"].search(
            [("user_id", "=", self.env.uid), ("task_id", "=", self.id)], limit=1
        )
        if not timer:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Log Time"),
            "res_model": "cimalor.project.timer.stop",
            "view_mode": "form",
            "target": "new",
            "context": {"default_timer_id": timer.id},
        }

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
