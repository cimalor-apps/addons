from odoo import fields, models, tools
from odoo.tools import SQL

from ..models.project_project_stage import STATE_TYPE_SELECTION

DUE_STATUS_SELECTION = [
    ("overdue", "Overdue"),
    ("upcoming", "Upcoming"),
    ("no_date", "No Date"),
]


class CimalorProjectWorkloadReport(models.Model):
    """Reporting › Workload: the hours still to do, per person.

    One row per open main task and person, read from a database view (the
    pattern of Project's own Tasks Analysis, report.project.task.user), so
    the pivot and the graph always show the current figures without any
    scheduled job. Read only: the rows change when the tasks do.

    The rules are those of the spec (§4.7):
    - hours: the task's remaining hours (planned minus spent), never below
      zero; a task without planned hours counts zero;
    - several people on a task: the hours are split evenly;
    - nobody on a task: the hours go to the project manager;
    - main tasks only, as on the project form; finished projects are left out.

    The project state comes with each row, so Waiting and On Hold are counted
    but can be told apart (pivot columns, filters).
    """

    _name = "cimalor.project.workload.report"
    _description = "Workload Analysis"
    _auto = False
    _order = "date, project_id"

    user_id = fields.Many2one(comodel_name="res.users", string="Person", readonly=True)
    task_id = fields.Many2one(comodel_name="project.task", readonly=True)
    project_id = fields.Many2one(comodel_name="project.project", readonly=True)
    partner_id = fields.Many2one(
        comodel_name="res.partner", string="Customer", readonly=True
    )
    manager_id = fields.Many2one(
        comodel_name="res.users", string="Project Manager", readonly=True
    )
    stage_id = fields.Many2one(
        comodel_name="project.project.stage", string="Project Stage", readonly=True
    )
    state_type = fields.Selection(
        selection=STATE_TYPE_SELECTION, string="Project State", readonly=True
    )
    date = fields.Date(
        string="Due Date",
        readonly=True,
        help="The task's deadline or, when it has none, the project's delivery date.",
    )
    due_status = fields.Selection(
        selection=DUE_STATUS_SELECTION, string="Due", readonly=True
    )
    hours = fields.Float(string="Pending Hours", readonly=True, aggregator="sum")
    company_id = fields.Many2one(comodel_name="res.company", readonly=True)

    def _query(self):
        """The rows of the report, one per open main task and person.

        Static SQL, without any value from the user: the view is created once,
        at install and upgrade, and Odoo applies the access rules on top of it
        when reading.

        - The assignee count splits the hours; a task without assignees gets
          one row for the project manager (LEFT JOIN, then COALESCE).
        - The task's deadline is a datetime stored in UTC; its date is enough
          to place the hours in a week.
        - due_status compares with CURRENT_DATE when the report is read, not
          when the view was created.
        - is_template exists on projects and tasks in 19.0 only: the 18.0
          port drops those two conditions.
        """
        return SQL("""
            SELECT
                ROW_NUMBER() OVER (ORDER BY task.id, assignee.user_id) AS id,
                COALESCE(assignee.user_id, project.user_id) AS user_id,
                task.id AS task_id,
                project.id AS project_id,
                project.partner_id AS partner_id,
                project.user_id AS manager_id,
                project.stage_id AS stage_id,
                project.cimalor_state_type AS state_type,
                COALESCE(task.date_deadline::date, project.date) AS date,
                CASE
                    WHEN COALESCE(task.date_deadline::date, project.date) IS NULL
                        THEN 'no_date'
                    WHEN COALESCE(task.date_deadline::date, project.date)
                        < CURRENT_DATE
                        THEN 'overdue'
                    ELSE 'upcoming'
                END AS due_status,
                GREATEST(COALESCE(task.remaining_hours, 0), 0)
                    / COALESCE(assignees.total, 1) AS hours,
                COALESCE(task.company_id, project.company_id) AS company_id
            FROM project_task AS task
            JOIN project_project AS project ON project.id = task.project_id
            LEFT JOIN project_task_user_rel AS assignee ON assignee.task_id = task.id
            LEFT JOIN (
                SELECT task_id, COUNT(*) AS total
                FROM project_task_user_rel
                GROUP BY task_id
            ) AS assignees ON assignees.task_id = task.id
            WHERE task.active
                AND project.active
                AND task.parent_id IS NULL
                AND task.state NOT IN ('1_done', '1_canceled')
                AND task.is_template IS NOT TRUE
                AND project.is_template IS NOT TRUE
                AND project.cimalor_state_type IS DISTINCT FROM 'done'
            """)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            SQL(
                "CREATE OR REPLACE VIEW %s AS (%s)",
                SQL.identifier(self._table),
                self._query(),
            )
        )
