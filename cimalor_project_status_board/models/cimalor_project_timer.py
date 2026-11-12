from odoo import fields, models


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
        """Hours since the start, rounded to the minute like a timesheet."""
        self.ensure_one()
        seconds = (fields.Datetime.now() - self.start).total_seconds()
        return round(max(seconds, 0) / 60) / 60

    def _cimalor_log_time(self, hours, description):
        """Log `hours` on the task as a standard timesheet line, then stop.

        Always through the ORM `create` of account.analytic.line, so billing,
        employee cost and the task's spent hours update as with any other
        timesheet (spec §6.1). hr_timesheet finds the employee from the user.
        The description is required by the stop dialog, not here: the rule
        is the timer's, and timesheets from other sources keep working.
        Under a minute (0 once rounded) the timer just stops: a zero-hour
        line is only noise.
        """
        for timer in self:
            if hours <= 0:
                continue
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
