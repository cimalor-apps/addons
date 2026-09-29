# Changelog

All notable changes to the Cimalor modules for Odoo 19.0. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow the Odoo Apps Store
convention `19.0.<major>.<minor>.<patch>`.

## cimalor_team_todo — Team To-Do

### [19.0.2.1.0] - 2026-09-09

#### Added

- Welcome task for each administrator on install, explaining shared stages, single
  ownership, roles and where to configure things. Same pattern as the onboarding to-do of
  Odoo's To-Do app: QWeb template rendered in the user's language, no notification sent,
  created only at install.

### [19.0.2.0.0] - 2026-09-09

#### Changed

- **Renamed** the module from `todo_team` to `cimalor_team_todo` and the display name from
  "ToDo Team" to "Team To-Do". Models are now `team.todo.task` and `team.todo.stage`. The
  previous name was never published, so there is no migration path from it.
- **One owner per task.** `user_id` replaces the former multiple assignees and is required.
  Reassigning a task removes it from the previous owner's board.
- Deadline shown on the kanban card with the `remaining_days` widget: red when overdue,
  orange when due today, hidden once the task is done.
- Manifest signature: author `Cimalor`, website `https://cimalor.com`.

#### Added

- Store listing: icon, description page (`static/description/index.html`) and screenshots.
- `README.md` for the module.

### [19.0.1.0.0] - 2026-08-31

- First version, as `todo_team`: team tasks with shared stages and several assignees, user
  and administrator roles, record rules, default stages, kanban/list/form views, Spanish
  translation and tests.

## cimalor_team_todo_project — Team To-Do: Project link

### [19.0.1.1.0] - 2026-09-09

#### Added

- The project name on the kanban card is a link that opens the task list of that project
  (`action_open_project_tasks`, delegating to the Project app).
- Project field in the search view and _Project_ group-by.
- Store listing: icon, description page and screenshot. `README.md` for the module.

#### Changed

- **Renamed** from `todo_team_project` to `cimalor_team_todo_project`; display name
  "Team To-Do: Project link".

### [19.0.1.0.0] - 2026-08-31

- First version, as `todo_team_project`: optional `project_id` on team tasks, shown on the
  form, list and kanban; auto-installed when the Project app is present.
