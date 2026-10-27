from odoo import fields, models

from .cimalor_project_stop_reason import DEPENDS_ON_SELECTION
from .project_project_stage import STATE_TYPE_SELECTION


class CimalorProjectStateLog(models.Model):
    """One row per change of a project's state: the history of the board.

    Rows are never edited. A correction is a new row, so the history always
    tells who said what and when (principle 6 of the spec). That is enforced
    by the access rights: users may create and read rows, never write or
    delete them.

    Everything is copied at the time of the change instead of read through
    related fields, so renaming a reason or retyping a stage later does not
    rewrite the past.
    """

    _name = "cimalor.project.state.log"
    _description = "Project State Change"
    _order = "date desc, id desc"
    _rec_name = "project_id"

    project_id = fields.Many2one(
        comodel_name="project.project",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="project_id.company_id",
        store=True,
        index=True,
    )
    date = fields.Datetime(required=True, default=fields.Datetime.now)
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Changed By",
        required=True,
        default=lambda self: self.env.user,
    )
    # set null rather than restrict: deleting a stage must stay possible, and
    # state_type keeps what the stage meant at the time.
    stage_id = fields.Many2one(
        comodel_name="project.project.stage",
        ondelete="set null",
    )
    state_type = fields.Selection(selection=STATE_TYPE_SELECTION)
    # restrict: a reason used in the history is archived, not deleted.
    reason_id = fields.Many2one(
        comodel_name="cimalor.project.stop.reason",
        ondelete="restrict",
    )
    depends_on = fields.Selection(selection=DEPENDS_ON_SELECTION)
    follow_up_date = fields.Date()
    restart_date = fields.Date()
    note = fields.Text()
