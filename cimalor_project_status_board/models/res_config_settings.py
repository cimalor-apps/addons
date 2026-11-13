from odoo import fields, models

from .project_project import EXCLUDED_DOMAIN_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # A filter on projects, edited with Odoo's domain editor, so each company
    # says with its own fields which projects the board leaves out (hour
    # banks, internal projects…). The module cannot know those fields.
    cimalor_excluded_project_domain = fields.Char(
        string="Excluded Projects",
        config_parameter=EXCLUDED_DOMAIN_PARAM,
        help="Projects matching this filter, such as hour banks, are left out of "
        "the boards, the reports and everybody's workload.",
    )

    def set_values(self):
        """Check the filter, save it and apply it to every project at once."""
        Project = self.env["project.project"]
        Project._cimalor_check_excluded_domain(self.cimalor_excluded_project_domain)
        result = super().set_values()
        Project._cimalor_refresh_excluded()
        return result
