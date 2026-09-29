# Team To-Do: Project link

Companion module for [Team To-Do](../cimalor_team_todo). It adds an optional link from each
team task to a project of the Project app.

## What it adds

- A `project_id` field on `team.todo.task` (optional, cleared if the project is deleted).
- The project on the kanban card, as a link that opens the task list of that project.
- A project column in the list view, a project field in the search view, and a _Project_
  group-by.

Team To-Do keeps working exactly the same for tasks without a project.

## Installation

Nothing to do. The module has `auto_install: True`: it is installed automatically as soon as
both `cimalor_team_todo` and `project` are present in the database.

## Access rights

A Team To-Do user does not need Project access rights. Reading projects and opening the
project's task list are granted to every internal user by the Project app itself.

## Technical notes

- The card link calls `action_open_project_tasks`, which delegates to
  `project.project.action_view_tasks()`. That is the method behind the _Tasks_ button of the
  Project app, so the behaviour follows whatever Odoo does in each version.
- The method is safe over RPC: it returns `False` when the task has no project.

### Running the tests

```bash
odoo -d test_db -i cimalor_team_todo_project --test-enable --test-tags /cimalor_team_todo_project --stop-after-init
```

## Support

- Email: soporte@cimalor.com
- Issues: https://github.com/cimalor-apps/addons/issues

We answer within 48 to 72 business hours.

## License

LGPL-3. See the `LICENSE` file. Copyright Cimalor, https://cimalor.com.
