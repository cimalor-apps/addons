from odoo import fields, models


class TeamTodoStage(models.Model):
    _name = "team.todo.stage"
    _description = "Task Stage"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(
        string="Folded in Kanban",
        help="If checked, the column is folded in the kanban view.",
    )
    is_done = fields.Boolean(
        string="Closing Stage",
        help="Tasks in this stage are considered done.",
    )
