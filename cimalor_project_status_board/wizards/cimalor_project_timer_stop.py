from odoo import api, fields, models
from odoo.exceptions import UserError


class CimalorProjectTimerStop(models.TransientModel):
    """The small dialog shown when a task timer is stopped.

    It proposes the elapsed time, lets the user correct it and asks for the
    comment, which is required: it is what the board shows on the project's
    card. Closing the dialog without confirming keeps the timer running, so
    no time is lost by a misclick.

    When the user pressed play on another task while this timer ran,
    `next_task_id` is that task: its timer starts once this one is logged.
    """

    _name = "cimalor.project.timer.stop"
    _description = "Stop Task Timer"

    timer_id = fields.Many2one(
        comodel_name="cimalor.project.timer",
        required=True,
        ondelete="cascade",
    )
    task_id = fields.Many2one(related="timer_id.task_id")
    project_id = fields.Many2one(related="timer_id.task_id.project_id")
    next_task_id = fields.Many2one(comodel_name="project.task")
    hours = fields.Float(
        string="Time Spent",
        compute="_compute_hours",
        store=True,
        readonly=False,
    )
    description = fields.Char(required=True)

    @api.depends("timer_id")
    def _compute_hours(self):
        for wizard in self:
            wizard.hours = wizard.timer_id._cimalor_elapsed_hours()

    def action_confirm(self):
        self.ensure_one()
        # Required in the view too; this also refuses a comment of spaces.
        if not self.description.strip():
            raise UserError(self.env._("Write what you did before logging the time."))
        # Read everything first: logging deletes the timer, and this dialog
        # goes with it (timer_id is ondelete cascade).
        next_task = self.next_task_id
        self.timer_id._cimalor_log_time(self.hours, self.description.strip())
        if next_task:
            self.env["cimalor.project.timer"].create({"task_id": next_task.id})
        return {"type": "ir.actions.act_window_close"}
