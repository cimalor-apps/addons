from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Capacity of a person for project tasks (spec §4.7): their working
    # schedule, minus approved time off, minus this time each working day.
    #
    # HR users only, as hr.employee asks of every field that is not on the
    # public profile (hr.employee.public): otherwise Odoo loads it whenever a
    # user without HR rights reads an employee, and refuses with an
    # AccessError (Enterprise timesheet validation does exactly that). The
    # capacity reads it as superuser, so nothing else changes.
    cimalor_admin_hours = fields.Float(
        string="Daily Admin Time",
        default=1.0,
        groups="hr.group_hr_user",
        help="Hours of each working day spent on meetings, email and other "
        "work outside project tasks. Subtracted from the working schedule to "
        "get the capacity for tasks.",
    )
