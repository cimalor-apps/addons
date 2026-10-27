from odoo import api, fields, models
from odoo.tools import format_date

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
    # View expressions cannot follow a relation (`cimalor_reason_id.requires_note`),
    # so the form needs this flag on the project itself to require the note.
    cimalor_reason_requires_note = fields.Boolean(
        related="cimalor_reason_id.requires_note",
    )
    cimalor_state_summary = fields.Char(
        string="State Summary",
        compute="_compute_cimalor_state_summary",
    )
    cimalor_follow_up_overdue = fields.Boolean(
        string="Follow-up Overdue",
        compute="_compute_cimalor_follow_up_overdue",
    )
    cimalor_state_log_ids = fields.One2many(
        comodel_name="cimalor.project.state.log",
        inverse_name="project_id",
        string="State History",
    )

    # The to-do list of the project form: main tasks only, as decided in the
    # spec. The domain on the field (not in the view) is what filters the
    # records the One2many reads.
    cimalor_open_task_ids = fields.One2many(
        comodel_name="project.task",
        inverse_name="project_id",
        string="Open Tasks",
        domain=[("parent_id", "=", False), ("is_closed", "=", False)],
    )
    cimalor_closed_task_ids = fields.One2many(
        comodel_name="project.task",
        inverse_name="project_id",
        string="Closed Tasks",
        domain=[("parent_id", "=", False), ("is_closed", "=", True)],
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

    @api.depends(
        "cimalor_state_type",
        "cimalor_reason_id",
        "cimalor_restart_date",
        "cimalor_state_note",
        "cimalor_missing_state_data",
        "cimalor_state_log_ids.state_type",
        "cimalor_state_log_ids.date",
    )
    def _compute_cimalor_state_summary(self):
        """The sentence shown on the kanban card for Waiting and On Hold.

        The other states get their sentence in 0.4, when the margins exist
        ("On time, ends on 27 Nov"). For catch-all reasons such as Other the
        note says more than the reason name, so the note is shown instead.
        """
        for project in self:
            state_type = project.cimalor_state_type
            summary = False
            if (
                state_type in ("waiting", "stopped")
                and project.cimalor_missing_state_data
            ):
                summary = (
                    self.env._("Waiting: reason or follow-up date missing")
                    if state_type == "waiting"
                    else self.env._("On hold: reason or restart date missing")
                )
            elif state_type == "waiting":
                reason = project._cimalor_reason_text()
                since = project._cimalor_state_since()
                summary = (
                    self.env._(
                        "Waiting since %(date)s: %(reason)s",
                        date=format_date(self.env, since),
                        reason=reason,
                    )
                    if since
                    else self.env._("Waiting: %(reason)s", reason=reason)
                )
            elif state_type == "stopped":
                summary = self.env._(
                    "On hold until %(date)s: %(reason)s",
                    date=format_date(self.env, project.cimalor_restart_date),
                    reason=project._cimalor_reason_text(),
                )
            project.cimalor_state_summary = summary

    @api.depends("cimalor_state_type", "cimalor_follow_up_date")
    def _compute_cimalor_follow_up_overdue(self):
        today = fields.Date.context_today(self)
        for project in self:
            project.cimalor_follow_up_overdue = (
                project.cimalor_state_type == "waiting"
                and bool(project.cimalor_follow_up_date)
                and project.cimalor_follow_up_date < today
            )

    def _cimalor_reason_text(self):
        self.ensure_one()
        reason = self.cimalor_reason_id
        if reason.requires_note and self.cimalor_state_note:
            return self.cimalor_state_note
        return reason.name

    def _cimalor_state_since(self):
        """Date the project entered its current state type, from the history.

        It walks the history back while the rows keep the same state type, so
        editing the reason or the date while still Waiting does not reset the
        count. Projects created before the module have no history and return
        False: the board then shows no date rather than a false one.
        """
        self.ensure_one()
        since = False
        for log in self.cimalor_state_log_ids:  # newest first, see _order
            if log.state_type != self.cimalor_state_type:
                break
            since = log.date
        return since and fields.Datetime.context_timestamp(self, since).date()

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
