import frappe

CC_ROLES = [
    "CC Super Admin",
    "CC Program Coordinator",
    "CC Teacher",
    "CC Student",
    "CC Parent",
]


def after_install():
    make_roles()
    make_workspace()
    frappe.db.commit()


def make_roles():
    for role in CC_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({
                "doctype": "Role",
                "role_name": role,
                "desk_access": 1 if role in ("CC Super Admin", "CC Program Coordinator", "CC Teacher") else 0,
            }).insert(ignore_permissions=True)


def make_workspace():
    """Link the app to Desk with its own workspace."""
    if frappe.db.exists("Workspace", "Curriculum Classroom"):
        return
    ws = frappe.get_doc({
        "doctype": "Workspace",
        "label": "Curriculum Classroom",
        "title": "Curriculum Classroom",
        "icon": "education",
        "module": "Curriculum Classroom",
        "public": 1,
        "shortcuts": [
            {"type": "URL", "label": "Open Web App (/classroom)", "url": "/classroom"},
            {"type": "DocType", "label": "CC Curriculum", "link_to": "CC Curriculum"},
            {"type": "DocType", "label": "CC Lesson (Library)", "link_to": "CC Lesson"},
            {"type": "DocType", "label": "CC Homework", "link_to": "CC Homework"},
            {"type": "DocType", "label": "CC Timetable", "link_to": "CC Timetable"},
            {"type": "DocType", "label": "CC Settings", "link_to": "CC Settings"},
        ],
        "links": [
            {"type": "Card Break", "label": "Teaching"},
            {"type": "Link", "link_type": "DocType", "label": "CC Curriculum", "link_to": "CC Curriculum"},
            {"type": "Link", "link_type": "DocType", "label": "CC Lesson", "link_to": "CC Lesson"},
            {"type": "Link", "link_type": "DocType", "label": "CC Homework", "link_to": "CC Homework"},
            {"type": "Link", "link_type": "DocType", "label": "CC Homework Submission", "link_to": "CC Homework Submission"},
            {"type": "Link", "link_type": "DocType", "label": "CC Timetable", "link_to": "CC Timetable"},
            {"type": "Card Break", "label": "Education Module"},
            {"type": "Link", "link_type": "DocType", "label": "Program", "link_to": "Program"},
            {"type": "Link", "link_type": "DocType", "label": "Course", "link_to": "Course"},
            {"type": "Link", "link_type": "DocType", "label": "Academic Year", "link_to": "Academic Year"},
            {"type": "Link", "link_type": "DocType", "label": "Academic Term", "link_to": "Academic Term"},
            {"type": "Link", "link_type": "DocType", "label": "Program Enrollment", "link_to": "Program Enrollment"},
            {"type": "Link", "link_type": "DocType", "label": "Student", "link_to": "Student"},
            {"type": "Link", "link_type": "DocType", "label": "Student Group", "link_to": "Student Group"},
            {"type": "Link", "link_type": "DocType", "label": "Guardian", "link_to": "Guardian"},
        ],
    })
    ws.insert(ignore_permissions=True)
