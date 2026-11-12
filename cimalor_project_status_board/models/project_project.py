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
    # The last timesheet comment of the project, shown on the kanban card next
    # to the state. Stored so the board reads it without one query per card.
    # Stored computes run as superuser, so every user who sees the project sees
    # the comment, even when hr_timesheet's rules hide the line itself from
    # them: the card tells how the project goes, the line stays private.
    cimalor_last_comment = fields.Char(
        string="Last Comment",
        compute="_compute_cimalor_last_comment",
        store=True,
    )
    cimalor_last_comment_date = fields.Date(
        string="Last Comment Date",
        compute="_compute_cimalor_last_comment",
        store=True,
    )
    cimalor_last_comment_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Last Comment By",
        compute="_compute_cimalor_last_comment",
        store=True,
    )
    # Tooltip of the green dot on the card: who is timing the project now.
    # compute_sudo: timers are private to their user (record rule), but the
    # card must show that somebody is working on the project. Only the names
    # leave the computation, never the timers themselves.
    cimalor_timer_running_by = fields.Char(
        string="Timer Running",
        compute="_compute_cimalor_timer_running_by",
        compute_sudo=True,
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

    @api.depends("cimalor_state_type", "cimalor_reason_id")
    def _compute_cimalor_depends_on(self):
        """Who the project depends on.

        Waiting always depends on the customer: it is not asked nor shown,
        but it is still stored (and copied to the history) so that later
        counters and panels can treat Waiting and On Hold alike.

        On Hold takes the reason's proposal, which the user can change: a
        lack of budget may be the customer's or ours.
        """
        for project in self:
            if project.cimalor_state_type == "waiting":
                project.cimalor_depends_on = "customer"
            else:
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

        It does not name the state: the card already sits in its column and
        the form shows the state buttons. So "Since 23/10/2026: reason" for
        Waiting and "Until 15/01/2027: reason" for On Hold.

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
                    self.env._("Reason or follow-up date missing")
                    if state_type == "waiting"
                    else self.env._("Reason or restart date missing")
                )
            elif state_type == "waiting":
                reason = project._cimalor_reason_text()
                since = project._cimalor_state_since()
                summary = (
                    self.env._(
                        "Since %(date)s: %(reason)s",
                        date=format_date(self.env, since),
                        reason=reason,
                    )
                    if since
                    else reason
                )
            elif state_type == "stopped":
                summary = self.env._(
                    "Until %(date)s: %(reason)s",
                    date=format_date(self.env, project.cimalor_restart_date),
                    reason=project._cimalor_reason_text(),
                )
            project.cimalor_state_summary = summary

    def _compute_cimalor_timer_running_by(self):
        """Who is timing the project, as "Timer running: Ana Ruiz, Luis Martín".

        Empty when nobody is.

        Not stored and without @api.depends: timers start and stop all day,
        so it is recomputed on every read. One search for all the projects of
        the board, not one per card.
        """
        timers = self.env["cimalor.project.timer"].search(
            [("task_id.project_id", "in", self.ids)]
        )
        names = {}
        for timer in timers:
            names.setdefault(timer.task_id.project_id.id, set()).add(timer.user_id.name)
        for project in self:
            users = names.get(project.id)
            project.cimalor_timer_running_by = users and self.env._(
                "Timer running: %(users)s", users=", ".join(sorted(users))
            )

    @api.depends("timesheet_ids.name", "timesheet_ids.date", "timesheet_ids.user_id")
    def _compute_cimalor_last_comment(self):
        """Description of the latest timesheet line that has one.

        Any line counts, from the timer, the Timesheets app or an import:
        latest date first, then latest created. The sort is explicit because
        a line just created is appended to the cached One2many, not sorted.
        Lines logged without a description are skipped: hr_timesheet stores
        them as "/".
        """
        for project in self:
            line = project.timesheet_ids.filtered(
                lambda line: line.name and line.name.strip() not in ("", "/")
            ).sorted(lambda line: (line.date, line.id), reverse=True)[:1]
            project.cimalor_last_comment = line.name
            project.cimalor_last_comment_date = line.date
            project.cimalor_last_comment_user_id = line.user_id

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
        changed = self.filtered(
            lambda project: project._cimalor_state_snapshot() != before[project.id]
        )
        changed._cimalor_log_state()
        changed._cimalor_post_state_note()
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

    def _cimalor_post_state_note(self):
        """Tell the chatter why a project is waiting or on hold.

        Project already posts a tracking line for every stage change
        ("Stage: In Progress → Waiting"), so a note is only added where it
        says something more: the reason and the date, plus who the project
        depends on when it is on hold (Waiting is always the customer), or
        that they are still missing after a drag. An internal note
        (mail.mt_note) does not notify the followers. The body is plain text,
        which message_post escapes.
        """
        depends_on_labels = dict(
            self._fields["cimalor_depends_on"]._description_selection(self.env)
        )
        for project in self:
            body = project._cimalor_state_note_body(depends_on_labels)
            if body:
                project.message_post(body=body, subtype_xmlid="mail.mt_note")

    def _cimalor_state_note_body(self, depends_on_labels):
        self.ensure_one()
        state_type = self.cimalor_state_type
        if state_type not in ("waiting", "stopped"):
            return False
        if self.cimalor_missing_state_data:
            return (
                self.env._("Waiting: the reason or the follow-up date is missing.")
                if state_type == "waiting"
                else self.env._("On hold: the reason or the restart date is missing.")
            )
        if state_type == "waiting":
            return self.env._(
                "Waiting for: %(reason)s. Follow-up on %(date)s.",
                reason=self._cimalor_reason_text(),
                date=format_date(self.env, self.cimalor_follow_up_date),
            )
        return self.env._(
            "On hold: %(reason)s. Depends on: %(depends_on)s. Restart on %(date)s.",
            reason=self._cimalor_reason_text(),
            depends_on=depends_on_labels.get(self.cimalor_depends_on, ""),
            date=format_date(self.env, self.cimalor_restart_date),
        )
