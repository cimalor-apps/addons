from odoo import fields, models

# Shared with the state log, which copies the type at the time of each change.
STATE_TYPE_SELECTION = [
    ("to_start", "To Start"),
    ("in_progress", "In Progress"),
    ("waiting", "Waiting"),
    ("stopped", "On Hold"),
    ("done", "Done"),
]


class ProjectProjectStage(models.Model):
    _inherit = "project.project.stage"

    # What the column means in the project lifecycle. Every rule of the module
    # reads this type and never the stage name, which customers rename, nor
    # `fold`, which only decides how the column is drawn. Empty means the
    # module applies no logic to the stage.
    cimalor_state_type = fields.Selection(
        selection=STATE_TYPE_SELECTION,
        string="State Type",
        help="Lifecycle meaning of the stage for Project Status Board. "
        "Waiting and On Hold ask for a reason and a date.",
    )
