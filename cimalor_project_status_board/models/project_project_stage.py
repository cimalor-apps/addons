from odoo import fields, models


class ProjectProjectStage(models.Model):
    _inherit = "project.project.stage"

    # What the column means in the project lifecycle. Every rule of the module
    # reads this type and never the stage name, which customers rename, nor
    # `fold`, which only decides how the column is drawn. Empty means the
    # module applies no logic to the stage.
    cimalor_state_type = fields.Selection(
        selection=[
            ("to_start", "To Start"),
            ("in_progress", "In Progress"),
            ("waiting", "Waiting"),
            ("stopped", "On Hold"),
            ("done", "Done"),
        ],
        string="State Type",
        help="Lifecycle meaning of the stage for Project Status Board. "
        "Waiting and On Hold ask for a reason and a date.",
    )
