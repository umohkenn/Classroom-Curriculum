# Curriculum Classroom - whitelisted API for the /classroom web app.
# All AI calls run server-side using the key stored in CC Settings.

import base64
import json

import frappe
import requests
from frappe import _
from frappe.utils import getdate, now_datetime, nowdate

STAFF = ("System Manager", "CC Super Admin", "CC Program Coordinator", "CC Teacher")

DOC_FIELDS = {
    "lesson_plan": "Write a complete, professional LESSON PLAN. Include: Subject, Class, Topic, Duration, Term/Week, Behavioural Objectives ('by the end of the lesson students should be able to...'), Instructional Materials, Previous Knowledge, Set Induction, Presentation in numbered steps (teacher and student activities per step - a table works well), Evaluation questions, Summary, Assignment.",
    "teacher_notes": "Write TEACHER'S NOTES: an in-depth content guide for the teacher. Full subject matter with correct terminology, difficult concepts explained, common misconceptions and how to address them, worked examples, teaching tips, discussion questions.",
    "lesson_notes": "Write formal LESSON NOTES: the structured content of the lesson under clear headings, with definitions, explanations and examples - exactly what will be taught.",
    "student_notes": "Write STUDENT NOTES: a simplified, student-friendly version learners can copy or study from. Simple language for the class level, short paragraphs, clear definitions, memorable examples, ending with 3-5 key points to remember.",
    "assessment": "Write an ASSESSMENT. Section A: 5-10 multiple-choice questions (options A-D). Section B: 3-5 theory questions. End with a MARKING GUIDE covering every question with marks. Match difficulty to the class level and objectives.",
}

VISUALS = (
    "Where they genuinely aid understanding include visuals: Markdown tables for structured "
    "content or mark schemes, and simple labelled diagrams as inline SVG inside a ```svg fenced "
    "code block (viewBox about 600x360, transparent background, sans-serif, clear labels, no "
    "external images). Keep diagrams simple and legible."
)


# ---------------------------------------------------------------- role helpers
def _roles():
    return set(frappe.get_roles(frappe.session.user))


def cc_role():
    r = _roles()
    for role in ("CC Super Admin", "CC Program Coordinator", "CC Teacher", "CC Student", "CC Parent"):
        if role in r:
            return role
    if "System Manager" in r or "Administrator" == frappe.session.user:
        return "CC Super Admin"
    return None


def _require(*allowed):
    role = cc_role()
    if role not in allowed:
        frappe.throw(_("Not permitted for your role"), frappe.PermissionError)
    return role


def _edu_installed():
    return frappe.db.exists("DocType", "Program")


def _my_student():
    """Student record linked to the logged-in user."""
    return frappe.db.get_value(
        "Student", {"user": frappe.session.user}, ["name", "student_name"], as_dict=True
    ) or frappe.db.get_value(
        "Student", {"student_email_id": frappe.session.user}, ["name", "student_name"], as_dict=True
    )


def _my_children():
    """Students linked to the logged-in Guardian (parent)."""
    guardian = frappe.db.get_value("Guardian", {"user": frappe.session.user}, "name") or \
        frappe.db.get_value("Guardian", {"email_address": frappe.session.user}, "name")
    if not guardian:
        return []
    rows = frappe.get_all("Student Guardian", filters={"guardian": guardian},
                          fields=["parent"], parent_doctype="Student")
    out = []
    for r in rows:
        st = frappe.db.get_value("Student", r.parent, ["name", "student_name"], as_dict=True)
        if st:
            out.append(st)
    return out


# ---------------------------------------------------------------- bootstrap
@frappe.whitelist()
def bootstrap():
    role = cc_role()
    settings = frappe.get_cached_doc("CC Settings")
    out = {
        "user": frappe.session.user,
        "full_name": frappe.utils.get_fullname(frappe.session.user),
        "role": role,
        "education_installed": bool(_edu_installed()),
        "branding": {
            "school_name": settings.school_name,
            "motto": settings.motto,
            "address": settings.address,
            "logo": settings.logo,
            "accent": settings.accent_color or "#22d3ee",
        },
        "has_api_key": bool(settings.get_password("anthropic_api_key", raise_exception=False)),
    }
    if role == "CC Student":
        out["student"] = _my_student()
    if role == "CC Parent":
        out["children"] = _my_children()
    return out


# ---------------------------------------------------------------- education pulls
@frappe.whitelist()
def programs():
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    if not _edu_installed():
        return []
    out = frappe.get_all("Program", fields=["name", "program_name", "program_abbreviation"],
                         order_by="program_name")
    for p in out:
        p["courses"] = [c.course for c in frappe.get_all(
            "Program Course", filters={"parent": p.name}, fields=["course"],
            parent_doctype="Program", order_by="idx")]
    return out


@frappe.whitelist()
def course_meta(course):
    doc = frappe.db.get_value("Course", course, ["course_name", "department"], as_dict=True) or {}
    doc["name"] = course
    return doc


@frappe.whitelist()
def academic_calendar():
    if not _edu_installed():
        return {"years": [], "terms": []}
    years = frappe.get_all("Academic Year", fields=["name", "year_start_date", "year_end_date"],
                           order_by="year_start_date desc")
    terms = frappe.get_all("Academic Term",
                           fields=["name", "academic_year", "term_name", "term_start_date", "term_end_date"],
                           order_by="term_start_date")
    return {"years": years, "terms": terms}


@frappe.whitelist()
def enrollment(program=None, academic_year=None, academic_term=None):
    """Student enrollment per term via Program Enrollment."""
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    if not _edu_installed():
        return []
    filters = {"docstatus": ["<", 2]}
    if program:
        filters["program"] = program
    if academic_year:
        filters["academic_year"] = academic_year
    if academic_term:
        filters["academic_term"] = academic_term
    rows = frappe.get_all("Program Enrollment", filters=filters,
                          fields=["name", "student", "student_name", "program",
                                  "academic_year", "academic_term", "enrollment_date"],
                          order_by="student_name", limit_page_length=500)
    return rows


@frappe.whitelist()
def guardians_of(student):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    rows = frappe.get_all("Student Guardian", filters={"parent": student},
                          fields=["guardian", "guardian_name", "relation"],
                          parent_doctype="Student")
    for r in rows:
        r["email"], r["mobile"] = frappe.db.get_value(
            "Guardian", r.guardian, ["email_address", "mobile_number"]) or (None, None)
    return rows


@frappe.whitelist()
def student_groups(program=None):
    if not _edu_installed():
        return []
    filters = {}
    if program:
        filters["program"] = program
    groups = frappe.get_all("Student Group", filters=filters,
                            fields=["name", "student_group_name", "program", "academic_year", "group_based_on"],
                            order_by="student_group_name")
    return groups


@frappe.whitelist()
def group_students(student_group):
    rows = frappe.get_all("Student Group Student", filters={"parent": student_group},
                          fields=["student", "student_name", "active"],
                          parent_doctype="Student Group", order_by="group_roll_number")
    return rows


# ---------------------------------------------------------------- curriculum
@frappe.whitelist()
def get_curriculum(program, course, academic_year=None, academic_term=None):
    filters = {"program": program, "course": course}
    if academic_year:
        filters["academic_year"] = academic_year
    name = frappe.db.get_value("CC Curriculum", filters, "name")
    if not name:
        name = frappe.db.get_value("CC Curriculum", {"program": program, "course": course}, "name")
    if not name:
        return None
    doc = frappe.get_doc("CC Curriculum", name)
    return _curriculum_dict(doc)


def _curriculum_dict(doc):
    return {
        "name": doc.name, "program": doc.program, "course": doc.course,
        "academic_year": doc.academic_year, "academic_term": doc.academic_term,
        "curriculum_file": doc.curriculum_file, "notes": doc.notes,
        "topics": [t.as_dict() for t in doc.topics],
    }


@frappe.whitelist()
def save_curriculum(program, course, academic_year=None, academic_term=None,
                    curriculum_file=None, notes=None):
    _require(*[r for r in STAFF if r != "System Manager"] + ["CC Super Admin"])
    name = frappe.db.get_value("CC Curriculum", {"program": program, "course": course}, "name")
    doc = frappe.get_doc("CC Curriculum", name) if name else frappe.new_doc("CC Curriculum")
    doc.update({"program": program, "course": course, "academic_year": academic_year,
                "academic_term": academic_term, "notes": notes})
    if curriculum_file:
        doc.curriculum_file = curriculum_file
    doc.save(ignore_permissions=False)
    return _curriculum_dict(doc)


@frappe.whitelist()
def update_topic(curriculum, row, patch):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    patch = frappe.parse_json(patch)
    doc = frappe.get_doc("CC Curriculum", curriculum)
    for t in doc.topics:
        if t.name == row:
            for k in ("topic_title", "term", "week_no", "objectives", "planned_date", "status"):
                if k in patch:
                    t.set(k, patch[k])
    doc.save()
    return _curriculum_dict(doc)


@frappe.whitelist()
def auto_plan(curriculum, start_date):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    doc = frappe.get_doc("CC Curriculum", curriculum)
    d = getdate(start_date)
    for i, t in enumerate(doc.topics):
        t.planned_date = frappe.utils.add_days(d, i * 7)
    doc.save()
    return _curriculum_dict(doc)


@frappe.whitelist()
def extract_topics(curriculum):
    """Read the attached curriculum file and AI-extract the scheme of work."""
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    doc = frappe.get_doc("CC Curriculum", curriculum)
    if not doc.curriculum_file:
        frappe.throw(_("Attach a curriculum file first"))
    blocks = _file_blocks(doc.curriculum_file)
    blocks.append({"type": "text", "text": (
        "Extract the scheme of work / list of teaching topics from this curriculum. "
        "Respond ONLY with compact JSON, no markdown fences, exactly this shape: "
        '{"topics":[{"title":"...","term":"First Term|Second Term|Third Term or empty",'
        '"week":<int or 0>,"objectives":"max 15 words"}]} '
        "List topics in teaching order, maximum 30."
    )})
    text = _claude(blocks)
    data = _json_from(text)
    doc.set("topics", [])
    for t in (data.get("topics") or [])[:30]:
        doc.append("topics", {
            "topic_title": t.get("title") or "Untitled topic",
            "term": t.get("term") or "",
            "week_no": int(t.get("week") or 0) or None,
            "objectives": t.get("objectives") or "",
            "status": "Pending",
        })
    doc.save()
    return _curriculum_dict(doc)


# ---------------------------------------------------------------- prepare / library
@frappe.whitelist()
def generate_documents(program, course, topic, doc_types, term=None, week=None,
                       klass=None, duration=None, extra=None, academic_year=None,
                       curriculum=None, topic_row=None):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    doc_types = frappe.parse_json(doc_types)
    context = [
        f"Subject / course: {frappe.db.get_value('Course', course, 'course_name') or course}",
        f"Programme / class: {klass or program}",
        f"Topic: {topic}",
    ]
    if duration:
        context.append(f"Lesson duration: {duration}")
    if term or week:
        context.append(f"Term / week: {term or ''} Week {week or ''}".strip())
    if extra:
        context.append(f"Curriculum / scheme extract:\n{extra}")

    base_blocks = []
    if curriculum:
        cfile = frappe.db.get_value("CC Curriculum", curriculum, "curriculum_file")
        if cfile:
            base_blocks = _file_blocks(cfile, optional=True)
            context.append("The official curriculum document is attached - use it as the primary source.")

    lesson = _get_or_make_lesson(program, course, topic, term, week, academic_year, duration)
    results = {}
    for dt in doc_types:
        if dt not in DOC_FIELDS:
            continue
        blocks = list(base_blocks)
        blocks.append({"type": "text", "text": (
            "You are an experienced teacher and curriculum specialist preparing classroom documents.\n\n"
            + "\n".join(context)
            + f"\n\nTask: {DOC_FIELDS[dt]}\n\n{VISUALS}\n\n"
            "Format in clean Markdown (## and ### headings, lists, tables). No preamble or closing "
            "remarks. Complete every section within the token budget."
        )})
        try:
            text = _claude(blocks)
            lesson.set(dt, text)
            results[dt] = {"ok": True, "content": text}
        except Exception as e:
            results[dt] = {"ok": False, "error": str(e)}
    lesson.save()
    if curriculum and topic_row:
        try:
            update_topic(curriculum, topic_row, json.dumps({"status": "Pending"}))
        except Exception:
            pass
    return {"lesson": lesson.name, "results": results}


def _get_or_make_lesson(program, course, topic, term, week, academic_year, duration):
    filters = {"program": program, "course": course, "topic": topic,
               "term": term or "", "week": int(week or 0) or 0}
    name = frappe.db.get_value("CC Lesson", filters, "name")
    if name:
        doc = frappe.get_doc("CC Lesson", name)
    else:
        doc = frappe.new_doc("CC Lesson")
        doc.update({"program": program, "course": course, "topic": topic,
                    "term": term, "week": int(week or 0) or None,
                    "academic_year": academic_year})
    if duration:
        doc.duration = duration
    return doc


@frappe.whitelist()
def library(course=None, program=None):
    filters = {}
    if course:
        filters["course"] = course
    if program:
        filters["program"] = program
    role = cc_role()
    fields = ["name", "program", "course", "topic", "term", "week", "modified",
              "lesson_plan", "teacher_notes", "lesson_notes", "student_notes", "assessment"]
    rows = frappe.get_all("CC Lesson", filters=filters, fields=fields,
                          order_by="term, week, topic", limit_page_length=500)
    out = []
    for r in rows:
        docs = {k: bool(r.get(k)) for k in DOC_FIELDS}
        mats = frappe.get_all("CC Lesson Material", filters={"parent": r.name},
                              fields=["name", "material_name", "material_type", "attachment", "url"],
                              parent_doctype="CC Lesson")
        entry = {"name": r.name, "program": r.program, "course": r.course, "topic": r.topic,
                 "term": r.term or "Unassigned term", "week": r.week or 0,
                 "docs": docs, "materials": mats}
        if role in ("CC Student", "CC Parent"):
            entry["docs"] = {"student_notes": docs.get("student_notes"),
                             "assessment": docs.get("assessment")}
        out.append(entry)
    return out


@frappe.whitelist()
def lesson_detail(name):
    doc = frappe.get_doc("CC Lesson", name)
    role = cc_role()
    allowed = list(DOC_FIELDS) if role in ("CC Super Admin", "CC Program Coordinator", "CC Teacher") \
        else ["student_notes"]
    return {
        "name": doc.name, "program": doc.program, "course": doc.course, "topic": doc.topic,
        "term": doc.term, "week": doc.week,
        "docs": {k: doc.get(k) for k in allowed if doc.get(k)},
        "materials": [m.as_dict() for m in doc.materials],
    }


@frappe.whitelist()
def add_material(lesson, material_name, material_type="Link", url=None, attachment=None):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    doc = frappe.get_doc("CC Lesson", lesson)
    doc.append("materials", {"material_name": material_name, "material_type": material_type,
                             "url": url, "attachment": attachment})
    doc.save()
    return lesson_detail(lesson)


@frappe.whitelist()
def remove_material(lesson, row):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    doc = frappe.get_doc("CC Lesson", lesson)
    doc.materials = [m for m in doc.materials if m.name != row]
    doc.save()
    return lesson_detail(lesson)


# ---------------------------------------------------------------- homework
@frappe.whitelist()
def homework_list(course=None, student_group=None):
    role = cc_role()
    filters = {}
    if course:
        filters["course"] = course
    if student_group:
        filters["student_group"] = student_group
    rows = frappe.get_all("CC Homework", filters=filters,
                          fields=["name", "title", "course", "program", "student_group",
                                  "due_date", "status"],
                          order_by="creation desc", limit_page_length=200)
    today = nowdate()
    student = _my_student() if role == "CC Student" else None
    out = []
    for r in rows:
        subs = frappe.get_all("CC Homework Submission", filters={"homework": r.name},
                              fields=["name", "student", "status", "score", "max_score",
                                      "submission_text"])
        if student:
            mine = [s for s in subs if s.student == student.name]
            if not mine and r.student_group:
                in_group = frappe.db.exists("Student Group Student",
                                            {"parent": r.student_group, "student": student.name})
                if not in_group:
                    continue
            r["my_submission"] = mine[0] if mine else None
        r["submitted"] = len([s for s in subs if s.status == "Submitted"])
        r["graded"] = len([s for s in subs if s.status == "Graded"])
        r["overdue"] = 1 if (r.due_date and str(r.due_date) < today and r.status == "Open") else 0
        out.append(r)
    return out


@frappe.whitelist()
def homework_create(title, course, content, program=None, student_group=None,
                    due_date=None, lesson=None):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    doc = frappe.get_doc({"doctype": "CC Homework", "title": title, "course": course,
                          "program": program, "student_group": student_group,
                          "due_date": due_date, "content": content, "lesson": lesson})
    doc.insert()
    # pre-create Pending submissions for the group so buckets work out of the box
    if student_group:
        for s in group_students(student_group):
            frappe.get_doc({"doctype": "CC Homework Submission", "homework": doc.name,
                            "student": s.student, "status": "Pending"}).insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def homework_detail(name):
    doc = frappe.get_doc("CC Homework", name)
    subs = frappe.get_all("CC Homework Submission", filters={"homework": name},
                          fields=["name", "student", "student_name", "status", "score",
                                  "max_score", "feedback", "submission_text", "submitted_on"],
                          order_by="student_name")
    role = cc_role()
    if role == "CC Student":
        me = _my_student()
        subs = [s for s in subs if me and s.student == me.name]
    if role == "CC Parent":
        kids = {c.name for c in _my_children()}
        subs = [s for s in subs if s.student in kids]
    return {"name": doc.name, "title": doc.title, "course": doc.course,
            "student_group": doc.student_group, "due_date": doc.due_date,
            "content": doc.content, "status": doc.status, "submissions": subs}


@frappe.whitelist()
def submit_homework(homework, text):
    role = _require("CC Student", "CC Teacher", "CC Program Coordinator", "CC Super Admin")
    me = _my_student()
    if role == "CC Student" and not me:
        frappe.throw(_("No Student record is linked to your user"))
    student = me.name if me else None
    name = frappe.db.get_value("CC Homework Submission",
                               {"homework": homework, "student": student}, "name")
    doc = frappe.get_doc("CC Homework Submission", name) if name else frappe.get_doc(
        {"doctype": "CC Homework Submission", "homework": homework, "student": student})
    doc.submission_text = text
    doc.submitted_on = now_datetime()
    if doc.status != "Graded":
        doc.status = "Submitted"
    doc.save(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def teacher_set_submission(submission=None, homework=None, student=None, text=None,
                           score=None):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    if not submission:
        submission = frappe.db.get_value("CC Homework Submission",
                                         {"homework": homework, "student": student}, "name")
    if not submission:
        doc = frappe.get_doc({"doctype": "CC Homework Submission", "homework": homework,
                              "student": student, "status": "Pending"})
        doc.insert(ignore_permissions=True)
        submission = doc.name
    doc = frappe.get_doc("CC Homework Submission", submission)
    if text is not None:
        doc.submission_text = text
        doc.submitted_on = now_datetime()
        if doc.status != "Graded":
            doc.status = "Submitted"
    if score is not None:
        doc.score = float(score)
    doc.save(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def grade_submission(submission):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    sub = frappe.get_doc("CC Homework Submission", submission)
    if not (sub.submission_text or "").strip():
        frappe.throw(_("Nothing submitted yet"))
    hw = frappe.get_doc("CC Homework", sub.homework)
    text = _claude([{"type": "text", "text": (
        "You are a fair, encouraging teacher grading homework.\n\n"
        f"ASSIGNMENT (with marking guide if present):\n{(hw.content or '')[:6000]}\n\n"
        f"STUDENT'S SUBMISSION ({sub.student_name}):\n{sub.submission_text[:6000]}\n\n"
        "Grade against the questions and marking guide. Respond ONLY with a JSON object, no "
        'fences: {"score": <number>, "max": <number>, "feedback": "<2-4 sentences to the student>"}'
    )}])
    data = _json_from(text)
    sub.score = float(data.get("score") or 0)
    sub.max_score = float(data.get("max") or 0)
    sub.feedback = data.get("feedback")
    sub.status = "Graded"
    sub.save(ignore_permissions=True)
    return sub.as_dict()


# ---------------------------------------------------------------- timetable
@frappe.whitelist()
def timetable_get(student_group):
    name = frappe.db.get_value("CC Timetable", {"student_group": student_group}, "name")
    if not name:
        return {"student_group": student_group, "slots": []}
    doc = frappe.get_doc("CC Timetable", name)
    return {"name": doc.name, "student_group": doc.student_group,
            "program": doc.program, "periods_per_day": doc.periods_per_day or 8,
            "slots": [s.as_dict() for s in doc.slots]}


@frappe.whitelist()
def timetable_save(student_group, slots, program=None, periods_per_day=8):
    _require("CC Super Admin", "CC Program Coordinator", "CC Teacher")
    slots = frappe.parse_json(slots)
    name = frappe.db.get_value("CC Timetable", {"student_group": student_group}, "name")
    doc = frappe.get_doc("CC Timetable", name) if name else frappe.new_doc("CC Timetable")
    doc.student_group = student_group
    doc.program = program
    doc.periods_per_day = int(periods_per_day or 8)
    doc.set("slots", [])
    for s in slots:
        doc.append("slots", {
            "day": s.get("day"), "period_no": int(s.get("period_no") or 1),
            "start_time": s.get("start_time"), "end_time": s.get("end_time"),
            "course": s.get("course"), "subject": s.get("subject"),
            "topic_title": s.get("topic_title"), "lesson": s.get("lesson"),
        })
    doc.save()
    return timetable_get(student_group)


@frappe.whitelist()
def my_timetable():
    role = cc_role()
    students = []
    if role == "CC Student":
        me = _my_student()
        students = [me.name] if me else []
    elif role == "CC Parent":
        students = [c.name for c in _my_children()]
    out = []
    for st in students:
        groups = frappe.get_all("Student Group Student", filters={"student": st},
                                fields=["parent"], parent_doctype="Student Group")
        for g in groups:
            tt = timetable_get(g.parent)
            if tt.get("slots"):
                tt["student"] = st
                out.append(tt)
    return out


# ---------------------------------------------------------------- dashboards
@frappe.whitelist()
def dashboard():
    role = cc_role()
    if role in ("CC Super Admin", "CC Program Coordinator"):
        return _admin_dashboard(role)
    if role == "CC Teacher":
        return _teacher_dashboard()
    if role == "CC Student":
        return _student_dashboard()
    if role == "CC Parent":
        return _parent_dashboard()
    return {"role": role, "cards": [], "charts": []}


def _coverage():
    total = frappe.db.count("CC Curriculum Topic") or 0
    done = frappe.db.count("CC Curriculum Topic", {"status": "Completed"}) or 0
    return total, done


def _grade_distribution():
    rows = frappe.get_all("CC Homework Submission", filters={"status": "Graded"},
                          fields=["score", "max_score"], limit_page_length=1000)
    bands = [0, 0, 0, 0, 0]  # <40, 40-54, 55-69, 70-84, 85+
    for r in rows:
        if not r.max_score:
            continue
        pct = r.score / r.max_score * 100
        bands[0 if pct < 40 else 1 if pct < 55 else 2 if pct < 70 else 3 if pct < 85 else 4] += 1
    return bands


def _admin_dashboard(role):
    total, done = _coverage()
    edu = _edu_installed()
    cards = [
        {"label": "Programs", "value": frappe.db.count("Program") if edu else 0, "icon": "layers"},
        {"label": "Courses", "value": frappe.db.count("Course") if edu else 0, "icon": "book"},
        {"label": "Students", "value": frappe.db.count("Student") if edu else 0, "icon": "users"},
        {"label": "Lessons in Library", "value": frappe.db.count("CC Lesson"), "icon": "folder"},
        {"label": "Curriculum Coverage", "value": f"{round(done/total*100) if total else 0}%", "icon": "target"},
        {"label": "Open Homework", "value": frappe.db.count("CC Homework", {"status": "Open"}), "icon": "clipboard"},
    ]
    lessons_by_course = frappe.db.sql(
        "select course, count(*) c from `tabCC Lesson` group by course order by c desc limit 6",
        as_dict=True)
    charts = [
        {"type": "donut", "title": "Curriculum coverage",
         "labels": ["Completed", "Pending"], "values": [done, max(total - done, 0)]},
        {"type": "bar", "title": "Lessons prepared per course",
         "labels": [r.course for r in lessons_by_course],
         "values": [r.c for r in lessons_by_course]},
        {"type": "bar", "title": "Grade distribution (all graded homework)",
         "labels": ["<40%", "40-54", "55-69", "70-84", "85+"],
         "values": _grade_distribution()},
    ]
    return {"role": role, "cards": cards, "charts": charts}


def _teacher_dashboard():
    total, done = _coverage()
    pending_grading = frappe.db.count("CC Homework Submission", {"status": "Submitted"})
    cards = [
        {"label": "My Lessons", "value": frappe.db.count("CC Lesson"), "icon": "folder"},
        {"label": "Topics Completed", "value": f"{done}/{total}", "icon": "target"},
        {"label": "Awaiting Grading", "value": pending_grading, "icon": "pen"},
        {"label": "Open Homework", "value": frappe.db.count("CC Homework", {"status": "Open"}), "icon": "clipboard"},
    ]
    charts = [
        {"type": "donut", "title": "Topic coverage",
         "labels": ["Completed", "Pending"], "values": [done, max(total - done, 0)]},
        {"type": "bar", "title": "Grade distribution",
         "labels": ["<40%", "40-54", "55-69", "70-84", "85+"], "values": _grade_distribution()},
    ]
    return {"role": "CC Teacher", "cards": cards, "charts": charts}


def _student_series(student):
    rows = frappe.get_all("CC Homework Submission",
                          filters={"student": student, "status": "Graded"},
                          fields=["homework", "score", "max_score", "modified"],
                          order_by="modified", limit_page_length=20)
    labels, values = [], []
    for r in rows:
        if r.max_score:
            labels.append(frappe.db.get_value("CC Homework", r.homework, "title") or r.homework)
            values.append(round(r.score / r.max_score * 100))
    return labels, values


def _buckets_for(student):
    today = nowdate()
    subs = frappe.get_all("CC Homework Submission", filters={"student": student},
                          fields=["name", "homework", "status", "score", "max_score",
                                  "submission_text"])
    b = {"overdue": 0, "pending": 0, "submitted": 0, "graded": 0}
    for s in subs:
        due = frappe.db.get_value("CC Homework", s.homework, "due_date")
        if s.status == "Graded":
            b["graded"] += 1
        elif (s.submission_text or "").strip():
            b["submitted"] += 1
        elif due and str(due) < today:
            b["overdue"] += 1
        else:
            b["pending"] += 1
    return b


def _student_dashboard():
    me = _my_student()
    if not me:
        return {"role": "CC Student", "cards": [], "charts": [],
                "note": "No Student record is linked to your login."}
    b = _buckets_for(me.name)
    labels, values = _student_series(me.name)
    avg = round(sum(values) / len(values)) if values else 0
    cards = [
        {"label": "Overdue", "value": b["overdue"], "icon": "alert", "tone": "red"},
        {"label": "Pending", "value": b["pending"], "icon": "clock", "tone": "amber"},
        {"label": "Submitted", "value": b["submitted"], "icon": "send", "tone": "blue"},
        {"label": "Graded", "value": b["graded"], "icon": "check", "tone": "green"},
        {"label": "Average Score", "value": f"{avg}%", "icon": "target"},
    ]
    charts = [{"type": "line", "title": "My scores over time", "labels": labels, "values": values}]
    return {"role": "CC Student", "cards": cards, "charts": charts, "student": me}


def _parent_dashboard():
    children = _my_children()
    cards, charts = [], []
    for c in children:
        b = _buckets_for(c.name)
        labels, values = _student_series(c.name)
        avg = round(sum(values) / len(values)) if values else 0
        cards.append({"label": c.student_name, "value": f"{avg}% avg",
                      "sub": f"{b['overdue']} overdue · {b['pending']} pending · {b['graded']} graded",
                      "icon": "user"})
        charts.append({"type": "line", "title": f"{c.student_name} - scores",
                       "labels": labels, "values": values})
    return {"role": "CC Parent", "cards": cards, "charts": charts, "children": children,
            "note": None if children else "No Guardian record matches your login email."}


# ---------------------------------------------------------------- AI plumbing
def _claude(blocks, max_tokens=None):
    s = frappe.get_cached_doc("CC Settings")
    key = s.get_password("anthropic_api_key", raise_exception=False)
    if not key:
        frappe.throw(_("Set the Anthropic API Key in CC Settings first"))
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": s.model or "claude-sonnet-4-6",
              "max_tokens": int(max_tokens or s.max_tokens or 1500),
              "messages": [{"role": "user", "content": blocks}]},
        timeout=180)
    data = resp.json()
    if data.get("error"):
        frappe.throw(data["error"].get("message") or "Anthropic API error")
    return "\n".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _json_from(text):
    clean = text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean[clean.index("{"): clean.rindex("}") + 1])


def _file_blocks(file_url, optional=False):
    """Turn an attached PDF/image into Anthropic content blocks; text files into a text block."""
    try:
        fdoc = frappe.get_doc("File", {"file_url": file_url})
        content = fdoc.get_content()
        name = (fdoc.file_name or "").lower()
        if isinstance(content, str):
            return [{"type": "text", "text": f"CURRICULUM TEXT:\n{content[:40000]}"}]
        b64 = base64.b64encode(content).decode()
        if name.endswith(".pdf"):
            return [{"type": "document",
                     "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}]
        for ext, mt in ((".png", "image/png"), (".jpg", "image/jpeg"), (".jpeg", "image/jpeg"),
                        (".webp", "image/webp"), (".gif", "image/gif")):
            if name.endswith(ext):
                return [{"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}}]
        try:
            return [{"type": "text", "text": f"CURRICULUM TEXT:\n{content.decode()[:40000]}"}]
        except Exception:
            return []
    except Exception:
        if optional:
            return []
        raise
