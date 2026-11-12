from odoo import api, fields, models


class CimalorProjectTimer(models.Model):
    """A task timer that is running for one user.

    A row exists only while the timer runs: starting creates it, stopping logs
    the time as a standard timesheet line and deletes it. Each user has at
    most one running timer (see project.task.action_cimalor_timer_start),
    and a record rule keeps each user's timers private.
    """

    _name = "cimalor.project.timer"
    _description = "Running Task Timer"
    _rec_name = "task_id"

    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
        index=True,
        default=lambda self: self.env.user,
        ondelete="cascade",
    )
    task_id = fields.Many2one(
        comodel_name="project.task",
        required=True,
        ondelete="cascade",
    )
    start = fields.Datetime(required=True, default=fields.Datetime.now)

    # The task's timer start and the card's green dot are computed from the
    # timers without @api.depends (they change all day and depend on who
    # looks). Within one request Odoo would keep the value it already read,
    # so starting or stopping a timer drops those cached values.
    @api.model_create_multi
    def create(self, vals_list):
        timers = super().create(vals_list)
        self._cimalor_invalidate_timer_fields()
        return timers

    def unlink(self):
        result = super().unlink()
        self._cimalor_invalidate_timer_fields()
        return result

    def _cimalor_invalidate_timer_fields(self):
        self.env["project.task"].invalidate_model(["cimalor_timer_start"])
        self.env["project.project"].invalidate_model(["cimalor_timer_running_by"])

    def _cimalor_stop_action(self, next_task=False):
        """The stop dialog of this timer; `next_task` starts after logging."""
        self.ensure_one()
        context = {"default_timer_id": self.id}
        if next_task:
            context["default_next_task_id"] = next_task.id
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Log Time"),
            "res_model": "cimalor.project.timer.stop",
            "view_mode": "form",
            "target": "new",
            "context": context,
        }

    def _cimalor_elapsed_hours(self):
        """Hours since the start, rounded to the minute, one minute at least."""
        self.ensure_one()
        seconds = (fields.Datetime.now() - self.start).total_seconds()
        return max(round(max(seconds, 0) / 60), 1) / 60

    def _cimalor_log_time(self, hours, description):
        """Log `hours` on the task as a standard timesheet line, then stop.

        Always through the ORM `create` of account.analytic.line, so billing,
        employee cost and the task's spent hours update as with any other
        timesheet (spec §6.1). hr_timesheet finds the employee from the user.
        The description is required by the stop dialog, not here: the rule
        is the timer's, and timesheets from other sources keep working.
        At least one minute is logged, even if the timer ran less or the
        hours were set to zero: the comment is required, and it is what the
        board shows, so it must always reach a timesheet line.
        """
        hours = max(hours, 1 / 60)
        for timer in self:
            task = timer.task_id
            self.env["account.analytic.line"].create(
                {
                    "name": description,
                    "task_id": task.id,
                    "project_id": task.project_id.id,
                    "user_id": timer.user_id.id,
                    "unit_amount": hours,
                    "date": fields.Date.context_today(timer),
                }
            )
        self.unlink()
