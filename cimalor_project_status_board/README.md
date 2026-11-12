# Project Status Board

Know which projects are moving, waiting or on hold, and why. For Odoo 19 with the Project
and Timesheets apps.

Project's stages tell you where a project is, not why it is stuck. Project Status Board turns
the stages into a board of states and asks for the missing piece when a project stops: what
it is waiting for, who it depends on and when to chase it again.

## Features

- **A board of projects by state:** To Start, In Progress, Waiting, On Hold and Done. Drag a
  card to change its state. On Hold is folded, so long pauses stay out of the way.
- **Waiting and On Hold ask for their data:** a reason and a follow-up or restart date. A
  Waiting project always waits on the customer; On Hold also records who it depends on
  (customer, supplier or us). A card dragged without its data is flagged until somebody
  fills it in.
- **The state sentence on every card**, such as _Since 23/10/2026: Approval of a delivery_
  in the Waiting column or _Until 15/01/2027: Customer postpones_ for On Hold, with the
  follow-up date in red once it has passed.
- **A project form for day-to-day work:** the state as a row of buttons, the main tasks as a
  to-do list with planned and spent hours, and the closed ones apart. Ticking a task closes
  it without touching its planned hours.
- **A timer on every task:** press play in the task list and a live counter starts; stop it
  to log the time as a standard timesheet line, with a required comment. One timer per
  person: pressing play on another task first asks for the running one's comment.
- **The last comment on every card:** "User · date · comment" of the project's latest
  timesheet comment, on one line under the state, whoever logged it and from wherever.
- **History of every state change:** who, when, the reason and the dates, never rewritten.
  The chatter gets a note each time a project starts waiting or goes on hold.
- **Configurable reasons**, ten to start with; On Hold ones propose who the project depends
  on.
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
  reason is used for Waiting or for On Hold and can require a note (as _Other_ does). On
  Hold reasons also propose who the project depends on.
- **Stages:** Project Status Board › Configuration › Stages, which is Project's own stage
  list. Set the **State Type** of each stage; a stage without a type is shown but gets no
  special behaviour. Several stages may share a type.

## Usage

- **Projects:** the board, grouped by stage. Drag a card to change its state; clicking it
  opens the project form.
- **Waiting / On Hold:** choose the reason and the date in the form. Waiting always depends
  on the customer and does not ask; for On Hold, who the project depends on is proposed by
  the reason and can be changed.
- **Tasks tab:** tick a task to close it, untick it in _Closed Tasks_ to reopen it. Add
  tasks with or without planned hours, and drag the handle to change their order.
- **Timer:** press ▷ on a task to start, ■ to stop. The dialog proposes the elapsed time
  (rounded to the minute), which you can correct, and asks what you did: the comment is
  required and becomes the card's last comment. _Keep Running_ closes it without stopping.
  Under a minute nothing is logged. Logging time needs your user to be linked to an
  employee, and the Timesheets user right. The comment is required only in this dialog:
  timesheets from the Timesheets app or imports keep their own rules.
- **State History tab:** every change of state with its author and data.

## Access rights

Project **users** can change the state of the projects they can see, which means writing on
projects (not creating or deleting them). Project **administrators** also manage the
reasons. Project's own record rules still decide which projects each user sees.

## Technical notes

- Models: `cimalor.project.state.log` (history, read and create only),
  `cimalor.project.stop.reason`, `cimalor.project.timer` (running timers, each user sees
  only their own) and the `cimalor.project.timer.stop` dialog; extensions of
  `project.project`, `project.project.stage` and `project.task`.
- The live counter is the module's only JavaScript: the `cimalor_timer` field widget, which
  shows "now minus start" every second, so it stays right after the computer sleeps.
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
