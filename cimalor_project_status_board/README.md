# Project Status Board

Know which projects are moving, waiting or on hold, and why. For Odoo 19 with the Project
and Timesheets apps.

Project's stages tell you where a project is, not why it is stuck. Project Status Board turns
the stages into a board of states and asks for the missing piece when a project stops: what
it is waiting for, who it depends on and when to chase it again.

## Features

- **A board of projects by state:** To Start, In Progress, Waiting, On Hold and Done. Drag a
  card to change its state. On Hold is folded, so long pauses stay out of the way.
- **Waiting and On Hold ask for their data:** a reason, who the project depends on (customer,
  supplier or us) and a follow-up or restart date. A card dragged without them is flagged
  until somebody fills them in.
- **The state sentence on every card**, such as _Waiting since 23/10/2026: Approval of a
  delivery_, with the follow-up date in red once it has passed.
- **A project form for day-to-day work:** the state as a row of buttons, the main tasks as a
  to-do list with planned and spent hours, and the closed ones apart. Ticking a task closes
  it without touching its planned hours.
- **History of every state change:** who, when, the reason and the dates, never rewritten.
  The chatter gets a note each time a project starts waiting or goes on hold.
- **Configurable reasons**, ten to start with, each proposing who the project depends on.
- Uses Project's own stages and tasks: no parallel data model, and the Project app keeps
  working exactly as before.

## Installation

Standard module installation. Dependencies: `project` and `hr_timesheet`.

On install the module:

- turns on the **Project Stages** setting of Project, which the board needs. Uninstalling
  does not turn it off: untick it under Project › Configuration › Settings if you want to;
- gives Project's four stages a state type (To Do: To Start, In Progress: In Progress,
  Done and Cancelled: Done) and adds two stages, **Waiting** and **On Hold**;
- loads ten starting reasons.

Projects created before the install have no history yet: it starts with their first state
change.

On uninstall, Waiting and On Hold are deleted only if no project (archived ones included)
is in them. A stage that still holds projects stays as an ordinary Project stage, so no
project loses its column. If you reinstall afterwards, the module adds a new Waiting or On
Hold stage next to the one that stayed: move the projects and delete the old one.

## Configuration

- **Reasons:** Project Status Board › Configuration › Reasons (Project administrators). Each
  reason is used for Waiting or for On Hold, proposes who the project depends on, and can
  require a note (as _Other_ does).
- **Stages:** Project Status Board › Configuration › Stages, which is Project's own stage
  list. Set the **State Type** of each stage; a stage without a type is shown but gets no
  special behaviour. Several stages may share a type.

## Usage

- **Projects:** the board, grouped by stage. Drag a card to change its state; clicking it
  opens the project form.
- **Waiting / On Hold:** choose the reason and the date in the form. Who the project depends
  on is proposed by the reason and can be changed.
- **Tasks tab:** tick a task to close it, untick it in _Closed Tasks_ to reopen it. Add
  tasks with or without planned hours.
- **State History tab:** every change of state with its author and data.

## Access rights

Project **users** can change the state of the projects they can see, which means writing on
projects (not creating or deleting them). Project **administrators** also manage the
reasons. Project's own record rules still decide which projects each user sees.

## Technical notes

- Models: `cimalor.project.state.log` (history, read and create only),
  `cimalor.project.stop.reason`; extensions of `project.project`, `project.project.stage`
  and `project.task`.
- The state type lives on the stage (`cimalor_state_type`); every rule reads it, never the
  stage name nor `fold`.
- `project.project.write()` is the single entry point of the history: the form, the kanban
  drag, imports and the API all log there.
- The board and the form are new views with priority 100, used only by this app's action,
  so Project's default views are unchanged.

### Running the tests

```bash
odoo -d test_db -i cimalor_project_status_board --test-enable --test-tags /cimalor_project_status_board --stop-after-init
```

### Translations

The template and the Spanish translation live in `i18n/`. Regenerate the template with:

```bash
odoo i18n export -d test_db -l pot -o cimalor_project_status_board.pot cimalor_project_status_board
```

Merge the new entries into `i18n/es.po` by hand instead of overwriting it: the export drops
translations that equal their source text and the `Language`/`Plural-Forms` header.

## Support

- Email: support@cimalor.com
- Issues: https://github.com/cimalor-apps/addons/issues

We aim to reply to email within 48 to 72 business hours. Issues have no fixed reply time.

## License

LGPL-3. See the `LICENSE` file. Copyright Cimalor, https://cimalor.com.
