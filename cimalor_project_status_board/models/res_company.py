from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Lists of people, so they live on the company and are edited in the
    # settings through related fields (the pattern of hr_expense's payment
    # methods): ir.config_parameter only keeps text.
    cimalor_excluded_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="cimalor_project_company_excluded_user_rel",
        column1="company_id",
        column2="user_id",
        string="Users Left Out of the Reports",
        help="People who do not appear in the team views of the reports (Team "
        "Activity, Workload, Capacity, Queue by Person, daily email), such as "
        "managers who do not log project work. Their tasks still count for the "
        "projects' margins.",
    )
    cimalor_digest_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="cimalor_project_company_digest_user_rel",
        column1="company_id",
        column2="user_id",
        string="Daily Email Recipients",
        help="People who receive the daily email of the board. Each one gets "
        "what they can see in the reports.",
    )
