from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

MODULE = "cimalor_project_status_board"
GROUPS = "project.group_project_user,hr_timesheet.group_hr_timesheet_user"


@tagged("post_install", "-at_install")
class TestProjectHoursMargin(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Margin worker"})
        cls.project = cls.env["project.project"].create(
            {
                "name": "Budgeted project",
                "allocated_hours": 20,
                "stage_id": cls.env.ref("project.project_project_stage_1").id,
            }
        )
        Task = cls.env["project.task"]
        cls.task_a, cls.task_b, cls.task_closed, cls.task_free = Task.create(
            [
                {"name": "A", "project_id": cls.project.id, "allocated_hours": 8},
                {"name": "B", "project_id": cls.project.id, "allocated_hours": 6},
                {
                    "name": "Closed",
                    "project_id": cls.project.id,
                    "allocated_hours": 5,
                    "state": "1_done",
                },
                {"name": "Not estimated", "project_id": cls.project.id},
            ]
        )
        Task.create(
            {
                "name": "Sub-task of A",
                "project_id": cls.project.id,
                "parent_id": cls.task_a.id,
                "allocated_hours": 3,
            }
        )

    def _log(self, task, hours):
        self.env["account.analytic.line"].create(
            {
                "name": "Work",
                "task_id": task.id,
                "project_id": self.project.id,
                "employee_id": self.employee.id,
                "unit_amount": hours,
            }
        )

    def test_pending_work_counts_open_main_tasks(self):
        """Closed tasks, sub-tasks and tasks without estimate add nothing."""
        self.assertEqual(self.project.cimalor_pending_hours, 14)

    def test_task_over_its_estimate_adds_nothing(self):
        self._log(self.task_b, 10)
        self.assertEqual(self.project.cimalor_pending_hours, 8)
        # 20 allocated - 10 spent - 8 pending
        self.assertEqual(self.project.cimalor_hours_margin, 2)

    def test_time_on_closed_tasks_uses_the_budget(self):
        self._log(self.task_closed, 4)
        self.assertEqual(self.project.cimalor_hours_margin, 2)
        self.assertEqual(self.project.cimalor_hours_health, "tight")

    def test_health_follows_the_margin(self):
        self.assertEqual(self.project.cimalor_hours_margin, 6)
        self.assertEqual(self.project.cimalor_hours_health, "ok")

        self.project.allocated_hours = 15  # margin 1, under 10 % of 15
        self.assertEqual(self.project.cimalor_hours_health, "tight")

        self.project.allocated_hours = 10  # margin -4
        self.assertEqual(self.project.cimalor_hours_margin, -4)
        self.assertEqual(self.project.cimalor_hours_health, "over")

    def test_no_budget_is_never_green(self):
        self.project.allocated_hours = 0
        self.assertEqual(self.project.cimalor_hours_health, "no_budget")

    def test_finished_project_has_no_health(self):
        self.project.stage_id = self.env.ref("project.project_project_stage_2")
        self.assertFalse(self.project.cimalor_hours_health)


@tagged("post_install", "-at_install")
class TestWorkloadReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ana = new_test_user(cls.env, login="psb_load_ana", groups=GROUPS)
        cls.luis = new_test_user(cls.env, login="psb_load_luis", groups=GROUPS)
        cls.boss = new_test_user(
            cls.env,
            login="psb_load_boss",
            groups=GROUPS + ",project.group_project_manager",
        )
        today = fields.Date.context_today(cls.env.user)
        cls.today = today
        Project = cls.env["project.project"]
        cls.moving = Project.create(
            {
                "name": "Moving",
                "user_id": cls.ana.id,
                "date": today + timedelta(days=10),
                "stage_id": cls.env.ref("project.project_project_stage_1").id,
            }
        )
        cls.waiting = Project.create(
            {
                "name": "Waiting",
                "stage_id": cls.env.ref(f"{MODULE}.project_project_stage_waiting").id,
            }
        )
        cls.done = Project.create(
            {
                "name": "Done",
                "stage_id": cls.env.ref("project.project_project_stage_2").id,
            }
        )
        Task = cls.env["project.task"]
        cls.shared, cls.unassigned, cls.late, _closed, _finished = Task.create(
            [
                {
                    "name": "Shared",
                    "project_id": cls.moving.id,
                    "allocated_hours": 10,
                    "user_ids": [cls.ana.id, cls.luis.id],
                },
                {
                    "name": "Nobody",
                    "project_id": cls.moving.id,
                    "allocated_hours": 4,
                    # Project assigns the creator by default.
                    "user_ids": False,
                },
                {
                    "name": "Late",
                    "project_id": cls.waiting.id,
                    "allocated_hours": 3,
                    "user_ids": [cls.luis.id],
                    "date_deadline": fields.Datetime.now() - timedelta(days=2),
                },
                {
                    "name": "Closed",
                    "project_id": cls.moving.id,
                    "allocated_hours": 7,
                    "user_ids": [cls.luis.id],
                    "state": "1_done",
                },
                {
                    "name": "In a finished project",
                    "project_id": cls.done.id,
                    "allocated_hours": 2,
                    "user_ids": [cls.luis.id],
                },
            ]
        )
        cls.Report = cls.env["cimalor.project.workload.report"]

    def _rows(self, user):
        # The report is a database view: write the pending ORM changes first.
        self.env.flush_all()
        return {
            (row.user_id, row.task_id): row
            for row in self.Report.with_user(user).search([])
            if row.project_id in (self.moving | self.waiting | self.done)
        }

    def test_rows_split_assign_and_date(self):
        rows = self._rows(self.boss)

        self.assertEqual(
            set(rows),
            {
                (self.ana, self.shared),
                (self.luis, self.shared),
                (self.ana, self.unassigned),
                (self.luis, self.late),
            },
            "closed tasks and finished projects are left out",
        )
        self.assertEqual(rows[self.ana, self.shared].hours, 5, "split evenly")
        self.assertEqual(rows[self.luis, self.shared].hours, 5)
        self.assertEqual(
            rows[self.ana, self.unassigned].hours, 4, "unassigned go to the manager"
        )

        shared = rows[self.ana, self.shared]
        self.assertEqual(shared.date, self.moving.date, "project date as fallback")
        self.assertEqual(shared.due_status, "upcoming")
        self.assertEqual(shared.state_type, "in_progress")

        late = rows[self.luis, self.late]
        self.assertEqual(late.due_status, "overdue")
        self.assertEqual(late.state_type, "waiting", "waiting counted, told apart")

    def test_each_person_sees_their_own_load(self):
        self.assertEqual({user for user, _task in self._rows(self.luis)}, {self.luis})
        self.assertEqual({user for user, _task in self._rows(self.ana)}, {self.ana})
        self.assertEqual(
            {user for user, _task in self._rows(self.boss)}, {self.ana, self.luis}
        )

    def test_report_opens(self):
        """The action's pivot, graph and list load for a project user."""
        action = self.env.ref(f"{MODULE}.action_cimalor_project_workload_report")
        Report = self.Report.with_user(self.luis)
        for view_type in action.view_mode.split(","):
            Report.get_views([(False, view_type)])
        Report.formatted_read_group([], ["user_id", "state_type"], ["hours:sum"])
