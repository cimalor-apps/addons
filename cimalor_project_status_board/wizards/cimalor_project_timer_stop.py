from odoo import api, fields, models


class CimalorProjectTimerStop(models.TransientModel):
    """The small dialog shown when a task timer is stopped.

    It proposes the elapsed time, lets the user correct it and add a
    description, and logs it. Closing the dialog without confirming keeps the
    timer running, so no time is lost by a misclick.
    """

    _name = "cimalor.project.timer.stop"
    _description = "Stop Task Timer"

    timer_id = fields.Many2one(
        comodel_name="cimalor.project.timer",
        required=True,
        ondelete="cascade",
    )
    task_id = fields.Many2one(related="timer_id.task_id")
    hours = fields.Float(
        string="Time Spent",
        compute="_compute_hours",
        store=True,
        readonly=False,
    )
    description = fields.Char()

    @api.depends("timer_id")
    def _compute_hours(self):
        for wizard in self:
            wizard.hours = wizard.timer_id._cimalor_elapsed_hours()

    def action_confirm(self):
        self.ensure_one()
        self.timer_id._cimalor_log_time(self.hours, self.description)
        return {"type": "ir.actions.act_window_close"}
