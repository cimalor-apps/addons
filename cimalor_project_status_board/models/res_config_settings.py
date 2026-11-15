from odoo import fields, models

from .cimalor_excluded import PROJECT_PARAM, TASK_PARAM, check_domain


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
        return result
