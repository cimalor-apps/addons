from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Capacity of a person for project tasks (spec §4.7): their working
    # schedule, minus approved time off, minus this time each working day.
    cimalor_admin_hours = fields.Float(
        string="Daily Admin Time",
        default=1.0,
        help="Hours of each working day spent on meetings, email and other "
        "work outside project tasks. Subtracted from the working schedule to "
        "get the capacity for tasks.",
    )
