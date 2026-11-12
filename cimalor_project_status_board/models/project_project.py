from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import format_date, plaintext2html

from .cimalor_project_queue import NEVER
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

# Hours health of a project (spec §4.6). "Tight" is a margin between zero
# and this share of the allocated hours: +5 h is room in a 10 h project and
# nothing in a 500 h one, so the threshold is relative.
HOURS_TIGHT_RATIO = 0.10

HOURS_HEALTH_SELECTION = [
    ("over", "Over Budget"),
    ("tight", "Tight"),
    ("ok", "Within Budget"),
    ("no_budget", "No Budget"),
]

# Days health (spec §4.8): "Tight" is a margin of this many working days or less.
DAYS_TIGHT = 2

DAYS_HEALTH_SELECTION = [
    ("late", "Late"),
    ("tight", "Tight"),
    ("ok", "On Time"),
    ("no_data", "No Forecast"),
]


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
    # Hours margin (spec §4.6): will the allocated hours be enough? Stored, so
    # the board can filter and group by it without computing every project.
    cimalor_pending_hours = fields.Float(
        string="Pending Work",
        compute="_compute_cimalor_pending_hours",
        store=True,
        help="Hours left on the open main tasks: planned minus spent, never "
        "below zero. Tasks without planned hours count zero.",
    )
    cimalor_hours_margin = fields.Float(
        string="Hours Margin",
        compute="_compute_cimalor_hours_margin",
        store=True,
        help="Allocated hours left minus pending work. Negative: the project "
        "will need more hours than allocated.",
    )
    cimalor_hours_health = fields.Selection(
        selection=HOURS_HEALTH_SELECTION,
        string="Hours Health",
        compute="_compute_cimalor_hours_margin",
        store=True,
    )
    # Days margin (spec §4.8): will the people on the project finish it by its
    # delivery date, given everything else they have to do? Computed when
    # read from the queue of every person (models/cimalor_project_queue.py),
    # never stored: it depends on other projects, which @api.depends cannot
    # follow. compute_sudo: the queue places this project's work among the
    # other projects and tasks of its people, which the user may not see;
    # only dates, a number and names come out.
    cimalor_forecast_end_date = fields.Date(
        string="Forecast End",
        compute="_compute_cimalor_days_margin",
        compute_sudo=True,
        help="Day the last open task ends if everybody works by due date at "
        "their capacity.",
    )
    cimalor_days_margin = fields.Integer(
        string="Days Margin",
        compute="_compute_cimalor_days_margin",
        compute_sudo=True,
        help="Working days from the forecast end to the delivery date. Negative: "
        "the project will be late.",
    )
    cimalor_days_health = fields.Selection(
        selection=DAYS_HEALTH_SELECTION,
        string="Days Health",
        compute="_compute_cimalor_days_margin",
        compute_sudo=True,
        search="_search_cimalor_days_health",
    )
    cimalor_late_by = fields.Char(
        string="Late Because Of",
        compute="_compute_cimalor_days_margin",
        compute_sudo=True,
        help="People whose part of the project ends after the delivery date.",
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

    @api.depends("task_ids.remaining_hours", "task_ids.state", "task_ids.parent_id")
    def _compute_cimalor_pending_hours(self):
        """Hours still to do on the open main tasks of the project.

        Main tasks only, as the to-do list of the form: sub-tasks are not
        used, and Odoo already subtracts their spent time from their parent's
        remaining hours. The task's remaining hours (hr_timesheet) are its
        planned minus spent; a task over its estimate adds nothing rather
        than lowering the total, and a task without estimate is zero.
        """
        for project in self:
            tasks = project.task_ids.filtered(
                lambda task: not task.parent_id and not task.is_closed
            )
            project.cimalor_pending_hours = sum(
                max(task.remaining_hours, 0.0) for task in tasks
            )

    @api.depends(
        "allocated_hours",
        "timesheet_ids.unit_amount",
        "cimalor_pending_hours",
        "cimalor_state_type",
    )
    def _compute_cimalor_hours_margin(self):
        """Allocated hours left (hr_timesheet's remaining hours) minus pending work.

        No health for a finished project, and "No Budget" (grey, never green)
        without allocated hours: the pending work alone would show a false
        red. Everything spent counts against the budget, closed tasks
        included.
        """
        for project in self:
            margin, health = 0.0, False
            if project.cimalor_state_type == "done":
                pass
            elif not project.allocated_hours:
                health = "no_budget"
            else:
                margin = project.remaining_hours - project.cimalor_pending_hours
                if margin < 0:
                    health = "over"
                elif margin <= project.allocated_hours * HOURS_TIGHT_RATIO:
                    health = "tight"
                else:
                    health = "ok"
            project.cimalor_hours_margin = margin
            project.cimalor_hours_health = health

    def _compute_cimalor_days_margin(self):
        """Forecast end, days margin and its health, from the work queue.

        One queue for all the projects being read (the whole board in one
        go). No health once done or on hold (on hold leaves the queue);
        "No Forecast" (grey, never green) without delivery date, without open
        tasks, or when somebody on it has no working schedule. Work beyond
        the queue's limit is late without a date.
        """
        Queue = self.env["cimalor.project.queue"]
        today = fields.Date.context_today(self)
        active = self.filtered(
            lambda p: p.cimalor_state_type not in ("done", "stopped")
        )
        forecast = Queue._project_forecast(today) if active else {}
        for project in self:
            end, margin, health, late_by = False, 0, False, False
            data = forecast.get(project.id)
            if project in active:
                health = "no_data"
                if data and data["end"] and project.date:
                    late = [
                        user_id
                        for user_id, user_end in data["users"].items()
                        if user_end > project.date
                    ]
                    late_by = ", ".join(
                        self.env["res.users"].browse(late).sorted("name").mapped("name")
                    )
                    if data["end"] == NEVER:
                        health = "late"
                    else:
                        end = data["end"]
                        margin = Queue._working_days_margin(
                            project.company_id.resource_calendar_id
                            or self.env.company.resource_calendar_id,
                            end,
                            project.date,
                        )
                        health = (
                            "late"
                            if margin < 0
                            else "tight" if margin <= DAYS_TIGHT else "ok"
                        )
                elif data and data["end"]:
                    end = data["end"] if data["end"] != NEVER else False
            project.cimalor_forecast_end_date = end
            project.cimalor_days_margin = margin
            project.cimalor_days_health = health
            project.cimalor_late_by = late_by or False

    def _search_cimalor_days_health(self, operator, value):
        """Find projects by days health, for the board filters.

        The health is not stored, so it is computed for the projects that can
        have one (not done, not on hold) and the matching ids returned.
        """
        # One value, or a collection (a list in 18.0, an OrderedSet in 19.0).
        values = {value} if isinstance(value, str) else set(value)
        projects = self.search([("cimalor_state_type", "not in", ["done", "stopped"])])
        matching = projects.filtered(lambda p: p.cimalor_days_health in values)
        negative = operator in ("!=", "not in")
        return [("id", "not in" if negative else "in", matching.ids)]

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
        if vals.get("date") and "date_start" not in vals:
            without_start = self.filtered(lambda project: not project.date_start)
            if without_start:
                without_start._cimalor_write_date_with_start(vals)
                others = self - without_start
                return others.write(vals) if others else True
        self._cimalor_check_write_access()
        if not set(STATE_FIELDS) & vals.keys():
            return super().write(vals)
        before = {project.id: project._cimalor_state_snapshot() for project in self}
        result = super().write(vals)
        changed = self.filtered(
            lambda project: project._cimalor_state_snapshot() != before[project.id]
        )
        changed._cimalor_log_state()
        changed._cimalor_post_state_note()
        changed._cimalor_notify_manager()
        return result

    def _cimalor_write_date_with_start(self, vals):
        """Save a new delivery date on projects that have no start date.

        Project treats its start and end dates as a range: its write() drops a
        new end date (`date`) on a project without start date, without any
        message. This app only shows the delivery date, so the change would
        silently not be saved. The start date is filled in with the day the
        project was created, or the delivery date when that is earlier
        (Project requires start <= end), and both are written together.
        """
        delivery = fields.Date.to_date(vals["date"])
        for project in self:
            start = min(project.create_date.date(), delivery)
            project.write(dict(vals, date_start=start))

    def _cimalor_check_write_access(self):
        """Project users may only change the projects they manage or work in.

        The module gives Project users write access to projects so they can
        change the state (ir.model.access.csv). It must not open every
        project they can see: only those they manage or have tasks in,
        closed tasks included, so finishing your task does not lock you out.

        This is checked here and not with a record rule because Odoo OR-s the
        rules of a user's groups, and Project already has a rule letting every
        employee access the projects they can see: a narrower rule would add
        nothing. Raising AccessError in write() is how Project itself limits
        what portal users may change on tasks. Superuser and Project
        administrators are not limited, as before the module.

        The task lookup runs as superuser: Project may hide some tasks of the
        project from the user, and only the answer "do I have one" is used.
        """
        if self.env.su or self.env.user.has_group("project.group_project_manager"):
            return
        user = self.env.user
        with_my_tasks = (
            self.env["project.task"]
            .sudo()
            .with_context(active_test=False)
            .search([("project_id", "in", self.ids), ("user_ids", "in", user.id)])
            .project_id
        )
        forbidden = self.filtered(
            lambda project: project.user_id != user and project not in with_my_tasks
        )
        if forbidden:
            raise AccessError(
                self.env._(
                    "You can only change projects you manage or have tasks in: "
                    "%(projects)s",
                    projects=", ".join(forbidden.mapped("display_name")),
                )
            )

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

    def _cimalor_notify_manager(self):
        """Tell the project manager when somebody else changes the state.

        Anybody with tasks in the project may change its state, so the board
        is updated when things happen; the manager gets a to-do activity to
        check it, and can undo it in one click. One open notice per project:
        a later change refreshes it instead of adding another.

        The refresh goes through sudo(): Odoo lets a user write only the
        activities they created or are assigned, and the notice may have been
        left by a colleague. It only touches this module's own activity type
        on this project.
        """
        activity_type = self.env.ref(
            "cimalor_project_status_board.mail_activity_type_state_change",
            raise_if_not_found=False,
        )
        if not activity_type:
            return
        depends_on_labels = dict(
            self._fields["cimalor_depends_on"]._description_selection(self.env)
        )
        for project in self:
            manager = project.user_id
            if not manager or manager == self.env.user:
                continue
            values = {
                "summary": self.env._(
                    "%(user)s moved the project to %(stage)s",
                    user=self.env.user.name,
                    stage=project.stage_id.name,
                ),
                "note": plaintext2html(
                    project._cimalor_state_note_body(depends_on_labels) or ""
                ),
                "date_deadline": fields.Date.context_today(project),
            }
            notice = project.sudo().activity_ids.filtered_domain(
                [
                    ("activity_type_id", "=", activity_type.id),
                    ("user_id", "=", manager.id),
                ]
            )[:1]
            if notice:
                notice.write(values)
            else:
                project.activity_schedule(
                    act_type_xmlid="cimalor_project_status_board."
                    "mail_activity_type_state_change",
                    user_id=manager.id,
                    **values,
                )

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
