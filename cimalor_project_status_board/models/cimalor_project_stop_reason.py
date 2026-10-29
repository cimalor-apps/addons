from odoo import fields, models

# Who a waiting or stopped project depends on. Shared by the reason, the
# project and the state log, so the three always offer the same choices.
DEPENDS_ON_SELECTION = [
    ("customer", "Customer"),
    ("supplier", "Supplier"),
    ("internal", "Us"),
]


class CimalorProjectStopReason(models.Model):
    _name = "cimalor.project.stop.reason"
    _description = "Project Waiting or Stop Reason"
    # Same order as the list, which sorts by its drag handle: the starting
    # data gives Waiting and On Hold reasons separate sequence ranges.
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    reason_type = fields.Selection(
        selection=[("waiting", "Waiting"), ("stopped", "On Hold")],
        string="Used For",
        required=True,
        help="A Waiting reason is offered only for Waiting projects, "
        "an On Hold reason only for projects on hold.",
    )
    depends_on = fields.Selection(
        selection=DEPENDS_ON_SELECTION,
        required=True,
        help="Proposed when the reason is chosen; it can still be changed "
        "on each project.",
    )
    requires_note = fields.Boolean(
        help="For catch-all reasons such as Other: the project must explain it "
        "in a note.",
    )
