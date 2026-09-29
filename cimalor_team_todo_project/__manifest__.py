{
    "name": "Team To-Do: Project link",
    "version": "18.0.1.1.0",
    "category": "Productivity",
    "summary": "Link Team To-Do tasks to the projects of the Project app",
    "description": """
Companion to Team To-Do: adds an optional link from each team task to a
project of the Project app. Installs itself when both are present.
    """,
    "author": "Cimalor",
    "website": "https://cimalor.com",
    "license": "LGPL-3",
    "depends": ["cimalor_team_todo", "project"],
    "images": ["static/description/main_screenshot.png"],
    "data": [
        "views/team_todo_task_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
