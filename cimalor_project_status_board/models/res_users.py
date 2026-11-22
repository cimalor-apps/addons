from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _cimalor_report_excluded_users(self):
        """Users to leave out of the team views of the reports.

        The users of the employees in the lists of the current companies
        (Settings › Employees Left Out of the Reports): the reports go by user,
        the one tasks and timesheets carry. The lists only trim the views of
        Project administrators, who see everybody: a person who only sees
        themselves keeps seeing themselves, listed or not.
        """
        if not self.env.user.has_group("project.group_project_manager"):
            return self.browse()
        # sudo: hr.employee is readable by HR officers only, and a Project
        # administrator may not be one. Only the linked users come out.
        employees = self.env.companies.sudo().cimalor_excluded_employee_ids
        return self.browse(employees.user_id.ids)

    @api.model
    def _cimalor_report_excluded_domain(self, field, operator, value):
        """Search domain of a report's "person left out" flag on `field`.

        For the action domains of Workload and Capacity, which cannot read the
        companies' lists themselves. `not in` keeps the rows without a person.
        """
        # One value, or a collection (a list in 18.0, an OrderedSet in 19.0).
        values = {value} if isinstance(value, bool) else set(value)
        wanted = {bool(item) for item in values}
        if operator in ("!=", "not in"):
            wanted = {True, False} - wanted
        excluded = self._cimalor_report_excluded_users()
        if wanted == {True, False}:
            return []
        if wanted == {True}:
            return [(field, "in", excluded.ids)]
        if wanted == {False}:
            return [(field, "not in", excluded.ids)]
        return [("id", "in", [])]
