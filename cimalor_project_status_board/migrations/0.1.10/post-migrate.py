"""0.1.10: the people left out of the reports are a list of employees, not users.

Each user of the old list becomes their active employee in the same company: an
archived one is shown nowhere, the reports included. The old relation table stays,
untouched: Odoo keeps it registered to the module and drops it on uninstall.

SQL, not the ORM: the old field no longer exists in the registry. A static
statement, without any value interpolated.
"""

from odoo.tools.sql import table_exists


def migrate(cr, version):
    if not version or not table_exists(cr, "cimalor_project_company_excluded_user_rel"):
        return
    cr.execute("""
        INSERT INTO cimalor_project_company_excluded_employee_rel
            (company_id, employee_id)
        SELECT DISTINCT old.company_id, employee.id
        FROM cimalor_project_company_excluded_user_rel AS old
        JOIN hr_employee AS employee
            ON employee.user_id = old.user_id
            AND employee.company_id = old.company_id
            AND employee.active
        ON CONFLICT DO NOTHING
        """)
