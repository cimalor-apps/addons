from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.project.models.project_task import CLOSED_STATES

from .cimalor_excluded import REFRESHING, TASK_PARAM, refresh_flags

# A change in any of these fields may open or close a request of an hour bank.
REQUEST_FIELDS = {"state", "project_id", "parent_id", "active", "cimalor_excluded"}


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

    # Tasks matching Settings › Excluded Tasks, such as the tasks that hold an
    # hour bank's balance: never counted as work. Stored for the Workload
    # database view; kept in step like the projects' flag.
    cimalor_excluded = fields.Boolean(
        string="Excluded from the Workload",
        readonly=True,
        copy=False,
        index=True,
        help="Matches the Excluded Tasks filter of the settings: its hours are a "
        "balance, not work, and never count in the board or the workload.",
    )

    @api.model
    def _cimalor_refresh_excluded(self, tasks=None):
        """Apply Settings › Excluded Tasks to `tasks` (every task when None)."""
        changed = refresh_flags(self, TASK_PARAM, tasks)
        changed.project_id._cimalor_sync_hour_bank_stage()

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        self._cimalor_refresh_excluded(tasks)
        tasks.project_id._cimalor_sync_hour_bank_stage()
        return tasks

    def write(self, vals):
        """Keep the exclusion flag and the hour banks' stage in step."""
        projects_before = self.project_id
        result = super().write(vals)
        if not self.env.context.get(REFRESHING):
            self._cimalor_refresh_excluded(self)
        if REQUEST_FIELDS & vals.keys():
            (projects_before | self.project_id)._cimalor_sync_hour_bank_stage()
        return result

    def unlink(self):
        projects = self.project_id
        result = super().unlink()
        projects.exists()._cimalor_sync_hour_bank_stage()
        return result

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

        One timer per user. If one is already running on another task, its
        stop dialog opens first, because every timesheet needs a comment;
        once it is logged, the dialog starts the timer on this task.
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
        running = Timer.search([("user_id", "=", self.env.uid)], limit=1)
        if running.task_id == self:
            return False
        if running:
            return running._cimalor_stop_action(next_task=self)
        Timer.create({"task_id": self.id})
        return False

    def action_cimalor_timer_stop(self):
        """Open the stop dialog to confirm the hours and write the comment."""
        self.ensure_one()
        timer = self.env["cimalor.project.timer"].search(
            [("user_id", "=", self.env.uid), ("task_id", "=", self.id)], limit=1
        )
        return timer._cimalor_stop_action() if timer else False

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
