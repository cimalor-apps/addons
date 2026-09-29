from odoo import fields, models


class TeamTodoTask(models.Model):
    _name = "team.todo.task"
    _description = "Team Task"
    _inherit = ["mail.thread"]
    _order = "sequence, id"

    name = fields.Char(string="Title", required=True, tracking=True)
    description = fields.Html()
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    priority = fields.Selection(
        [("0", "Normal"), ("1", "Important")],
        default="0",
    )
    deadline = fields.Date()

    # SHARED stage: it belongs to the task, not to the person looking at it.
    # This is the opposite of the personal stages of the Project app, where
    # each user drags the card in their own board.
    stage_id = fields.Many2one(
        comodel_name="team.todo.stage",
        required=True,
        default=lambda self: self._default_stage_id(),
        group_expand="_group_expand_stage_id",
        tracking=True,
    )
    # Done flag derived from the stage. Stored so it can be filtered and
    # grouped on.
    is_done = fields.Boolean(
        string="Done",
        related="stage_id.is_done",
        store=True,
    )
    # SINGLE assignee: exactly one person owns the task. Sharing the work
    # between several people is what makes the follow-up hard, so the model
    # forbids it instead of leaving it to discipline.
    # required, like stage_id: a task with no owner would also be a task no
    # plain user can see, because the record rule filters on this field.
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Assignee",
        required=True,
        default=lambda self: self.env.user,
        # Portal and public users are not staff: they cannot be given work.
        domain="[('share', '=', False)]",
        # The record rule filters every read by this column.
        index=True,
        tracking=True,
    )

    def _default_stage_id(self):
        return self.env["team.todo.stage"].search([], limit=1)

    def _group_expand_stage_id(self, stages, domain, *args):
        """Show every stage as a kanban column, even the empty ones.

        *args keeps this tolerant to signature changes between versions.
        """
        # pylint: disable=no-search-all
        # Loading them all is the whole point here, and stages are a small
        # configuration table, so the result set is bounded by design.
        return self.env["team.todo.stage"].search([])
