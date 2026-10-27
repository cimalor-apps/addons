from odoo import api, fields, models

from .cimalor_project_stop_reason import DEPENDS_ON_SELECTION

# A change in any of these fields is a change of the project's state and
# leaves one row in the state log.
STATE_FIELDS = (
    "stage_id",
    "cimalor_reason_id",
    "cimalor_depends_on",
    "cimalor_follow_up_date",
    "cimalor_restart_date",
    "cimalor_state_note",
)


class ProjectProject(models.Model):
    _inherit = "project.project"

    # Stored so projects can be searched and grouped by lifecycle state.
    cimalor_state_type = fields.Selection(
        related="stage_id.cimalor_state_type",
        store=True,
        string="State Type",
    )

    # Data of the current state, edited on the project form.
    #
    # They are computed, stored and editable (readonly=False): the compute
    # only runs when what it depends on changes, so it can clean up after a
    # stage change, while a value typed by the user is kept. Odoo does not
    # recompute a field that is being written, so saving the stage and the
    # reason together keeps the reason. Unlike an onchange, this also runs
    # when the stage changes from the kanban, an import or the API.
    cimalor_reason_id = fields.Many2one(
        comodel_name="cimalor.project.stop.reason",
        string="Reason",
        compute="_compute_cimalor_reason_id",
        store=True,
        readonly=False,
        ondelete="restrict",
        domain="[('reason_type', '=', cimalor_state_type)]",
    )
    cimalor_depends_on = fields.Selection(
        selection=DEPENDS_ON_SELECTION,
        string="Depends On",
        compute="_compute_cimalor_depends_on",
        store=True,
        readonly=False,
    )
    cimalor_follow_up_date = fields.Date(
        string="Follow-up Date",
        compute="_compute_cimalor_follow_up_date",
        store=True,
        readonly=False,
    )
    cimalor_restart_date = fields.Date(
        string="Restart Date",
        compute="_compute_cimalor_restart_date",
        store=True,
        readonly=False,
    )
    # Required by catch-all reasons such as Other (requires_note).
    cimalor_state_note = fields.Text(
        string="State Note",
        compute="_compute_cimalor_state_note",
        store=True,
        readonly=False,
    )
    cimalor_missing_state_data = fields.Boolean(
        string="State Data Missing",
        compute="_compute_cimalor_missing_state_data",
        help="Waiting or On Hold without its reason or date, typically after "
        "dragging the card on the board.",
    )
    cimalor_state_log_ids = fields.One2many(
        comodel_name="cimalor.project.state.log",
        inverse_name="project_id",
        string="State History",
    )

    @api.depends("cimalor_state_type")
    def _compute_cimalor_reason_id(self):
        """Drop the reason when the project leaves the state it was given for."""
        for project in self:
            reason = project.cimalor_reason_id
            if reason.reason_type != project.cimalor_state_type:
                reason = False
            project.cimalor_reason_id = reason

    @api.depends("cimalor_reason_id")
    def _compute_cimalor_depends_on(self):
        """Propose who the project depends on from the reason.

        It is only a proposal: "Information or material" may come from the
        customer or from a supplier, so the user can change it afterwards.
        """
        for project in self:
            project.cimalor_depends_on = project.cimalor_reason_id.depends_on

    @api.depends("cimalor_state_type")
    def _compute_cimalor_follow_up_date(self):
        for project in self:
            if project.cimalor_state_type != "waiting":
                project.cimalor_follow_up_date = False
            else:
                project.cimalor_follow_up_date = project.cimalor_follow_up_date

    @api.depends("cimalor_state_type")
    def _compute_cimalor_restart_date(self):
        for project in self:
            if project.cimalor_state_type != "stopped":
                project.cimalor_restart_date = False
            else:
                project.cimalor_restart_date = project.cimalor_restart_date

    @api.depends("cimalor_state_type")
    def _compute_cimalor_state_note(self):
        for project in self:
            if project.cimalor_state_type not in ("waiting", "stopped"):
                project.cimalor_state_note = False
            else:
                project.cimalor_state_note = project.cimalor_state_note

    @api.depends(
        "cimalor_state_type",
        "cimalor_reason_id",
        "cimalor_follow_up_date",
        "cimalor_restart_date",
        "cimalor_state_note",
    )
    def _compute_cimalor_missing_state_data(self):
        for project in self:
            state_date = {
                "waiting": project.cimalor_follow_up_date,
                "stopped": project.cimalor_restart_date,
            }
            state_type = project.cimalor_state_type
            reason = project.cimalor_reason_id
            project.cimalor_missing_state_data = state_type in state_date and (
                not reason
                or not state_date[state_type]
                or (reason.requires_note and not project.cimalor_state_note)
            )

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        projects._cimalor_log_state()
        return projects

    def write(self, vals):
        """Log the new state of every project whose state really changed.

        This is the single entry point of the history: the form, the kanban
        drag, an import or the API all end here. When the form saves the
        stage and its data together there is one write, so one log row with
        the data; a drag only sends the stage, so the row has no data.

        The snapshot comparison skips writes that change nothing, such as a
        form saved again with the same values.
        """
        if not set(STATE_FIELDS) & vals.keys():
            return super().write(vals)
        before = {project.id: project._cimalor_state_snapshot() for project in self}
        result = super().write(vals)
        self.filtered(
            lambda project: project._cimalor_state_snapshot() != before[project.id]
        )._cimalor_log_state()
        return result

    def _cimalor_state_snapshot(self):
        self.ensure_one()
        return tuple(self[field_name] for field_name in STATE_FIELDS)

    def _cimalor_log_state(self):
        """Add one state log row per project, copying its current state."""
        self.env["cimalor.project.state.log"].create(
            [
                {
                    "project_id": project.id,
                    "user_id": self.env.user.id,
                    "stage_id": project.stage_id.id,
                    "state_type": project.cimalor_state_type,
                    "reason_id": project.cimalor_reason_id.id,
                    "depends_on": project.cimalor_depends_on,
                    "follow_up_date": project.cimalor_follow_up_date,
                    "restart_date": project.cimalor_restart_date,
                    "note": project.cimalor_state_note,
                }
                for project in self
                if project.stage_id
            ]
        )
