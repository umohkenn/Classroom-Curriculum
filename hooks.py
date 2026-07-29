app_name = "curriculum_classroom"
app_title = "Curriculum Classroom"
app_publisher = "Curriculum Classroom"
app_description = "AI-assisted curriculum-to-classroom suite on top of Frappe Education"
app_email = "admin@example.com"
app_license = "MIT"
app_icon = "octicon octicon-book"
app_color = "#22d3ee"

after_install = "curriculum_classroom.setup.install.after_install"

# Web app served at /classroom (www/classroom/index.html)
website_route_rules = [
    {"from_route": "/classroom/<path:app_path>", "to_route": "classroom"},
]

# Show a link in the standard portal sidebar too
standard_portal_menu_items = [
    {"title": "Classroom", "route": "/classroom", "reference_doctype": "", "role": ""},
]

fixtures = []
