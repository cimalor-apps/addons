from odoo import api, fields, models

from .cimalor_excluded import PROJECT_PARAM, TASK_PARAM, check_domain

DIGEST_CRON = "cimalor_project_status_board.ir_cron_cimalor_project_digest"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Filters edited with Odoo's domain editor, so each company says with its
    # own fields what the board leaves out. The module cannot know those
    # fields: an hour bank flag, a tag, a type of project...
    cimalor_excluded_project_domain = fields.Char(
        string="Excluded Projects",
        config_parameter=PROJECT_PARAM,
        help="Projects matching this filter are left out of the boards, the "
        "reports and everybody's workload.",
    )
    cimalor_excluded_task_domain = fields.Char(
        string="Excluded Tasks",
        config_parameter=TASK_PARAM,
        help="Tasks matching this filter, such as the ones holding an hour bank's "
        "balance, never count as work. A project with such tasks is an hour bank: "
        "it goes on hold by itself without other open tasks, and back to In "
        "Progress with the next one.",
    )
    # Lists of people, kept on the company (see res.company).
    cimalor_excluded_employee_ids = fields.Many2many(
        related="company_id.cimalor_excluded_employee_ids",
        readonly=False,
    )
    cimalor_digest_user_ids = fields.Many2many(
        related="company_id.cimalor_digest_user_ids",
        readonly=False,
    )
    # The time of the daily email is the next run of its scheduled job, read
    # and written here as CRM does with its lead assignment: the job then
    # repeats every day at that time.
    cimalor_digest_next_send = fields.Datetime(
        string="Next Daily Email",
        compute="_compute_cimalor_digest_next_send",
        readonly=False,
        store=True,
    )

    @api.depends("company_id")
    def _compute_cimalor_digest_next_send(self):
        # sudo: scheduled jobs are technical records; only their next run is read.
        cron = self.env.ref(DIGEST_CRON, raise_if_not_found=False)
        for settings in self:
            settings.cimalor_digest_next_send = cron.sudo().nextcall if cron else False

    def set_values(self):
        """Check the filters, save them and apply them to every record at once."""
        Project = self.env["project.project"]
        Task = self.env["project.task"]
        check_domain(
            Project,
            self.cimalor_excluded_project_domain,
            self.env._("Excluded Projects"),
        )
        check_domain(
            Task, self.cimalor_excluded_task_domain, self.env._("Excluded Tasks")
        )
        result = super().set_values()
        Project._cimalor_refresh_excluded()
        Task._cimalor_refresh_excluded()
        # sudo: as for reading it; the settings are for administrators.
        cron = self.env.ref(DIGEST_CRON, raise_if_not_found=False)
        next_send = self.cimalor_digest_next_send
        if cron and next_send and cron.sudo().nextcall != next_send:
            cron.sudo().nextcall = next_send
        return result
