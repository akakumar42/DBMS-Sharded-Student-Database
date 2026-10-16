#!/usr/bin/python
"""Generate the students, courses and attendance tables with Faker.

  python data_generetor.py                  # create + fill the db tables
  python data_generetor.py db 50 8 200      # same, with custom row counts
  python data_generetor.py csv              # only write the CSV files

Columns match the SQLAlchemy models in features.py:
  students    -> id, name, email_id
  courses     -> id, course_name
  attendance  -> id, class_date, student_id, course_id, status

attendance references real student_id / course_id values so the foreign
keys stay valid.
"""

from faker import Faker
from sqlalchemy import inspect
import csv
import random
import sys

from features import RowCountSharding

faker = Faker()

# How many rows to generate for each table.
NUM_STUDENTS = 10000
NUM_COURSES = 20
NUM_ATTENDANCE = 30000

SUBJECTS = [
    "Databases", "Operating Systems", "Computer Networks", "Algorithms",
    "Machine Learning", "Web Development", "Cyber Security", "Data Structures",
    "Software Engineering", "Cloud Computing", "Artificial Intelligence",
    "Mathematics", "Statistics", "Discrete Maths", "Compiler Design",
    "Mobile Development", "Computer Graphics", "Distributed Systems",
    "Information Theory", "Digital Logic",
]
STATUSES = ["Present", "Absent"]


def write_students(path="students.csv", count=NUM_STUDENTS):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "email_id"])
        writer.writeheader()
        for i in range(1, count + 1):
            writer.writerow({"id": i, "name": faker.name(),
                "email_id": faker.email()})
    print(f"wrote {count} rows -> {path}")


def write_courses(path="courses.csv", count=NUM_COURSES):
    # Cap at the number of distinct subjects so names stay unique.
    count = min(count, len(SUBJECTS))
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "course_name"])
        writer.writeheader()
        for i in range(1, count + 1):
            writer.writerow({"id": i, "course_name": SUBJECTS[i - 1]})
    print(f"wrote {count} rows -> {path}")
    return count


def write_attendance(path="attendance.csv", count=NUM_ATTENDANCE,
        num_students=NUM_STUDENTS, num_courses=NUM_COURSES):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f,
            fieldnames=["id", "class_date", "student_id", "course_id", "status"])
        writer.writeheader()
        for i in range(1, count + 1):
            class_date = faker.date_between(start_date="-1y", end_date="today")
            writer.writerow({
                "id": i,
                "class_date": class_date.isoformat(),
                "student_id": random.randint(1, num_students),
                "course_id": random.randint(1, num_courses),
                "status": random.choice(STATUSES),
            })
    print(f"wrote {count} rows -> {path}")


def seed_database(db, num_students=20, num_courses=5, num_attendance=50):
    """Insert Faker rows straight into the sharded database (all 3 tables).

    db is a features.RowCountSharding. Courses that already exist are
    skipped; attendance picks from every student and course in the db.
    """
    existing = {course.course_name for course in db.all_courses()}
    for subject in [s for s in SUBJECTS if s not in existing][:num_courses]:
        db.add_course(subject)

    for _ in range(num_students):
        db.add_person(faker.name(), faker.email())

    student_ids = [person.id for _, person in db.all_people()]
    course_ids = [course.id for course in db.all_courses()]
    if not student_ids or not course_ids:
        print("need at least one student and one course for attendance")
        return

    for _ in range(num_attendance):
        class_date = faker.date_between(start_date="-1y", end_date="today")
        db.add_attendance(random.choice(student_ids), random.choice(course_ids),
            class_date.isoformat(), random.choice(STATUSES))
    print(f"seeded {num_students} students, {num_courses} courses, "
        f"{num_attendance} attendance rows")


def generate_tables(num_students=20, num_courses=5, num_attendance=50,
        folder="shards", rows_per_shard=3):
    """Create the students/courses/attendance tables and fill them with Faker.

    RowCountSharding runs Base.metadata.create_all on every shard, which
    creates the three tables (if missing) from the models in features.py.
    """
    db = RowCountSharding(folder=folder, rows_per_shard=rows_per_shard)
    for shard_number, engine in sorted(db.engines.items()):
        tables = ", ".join(inspect(engine).get_table_names())
        print(f"shard {shard_number:03d} tables: {tables}")

    seed_database(db, num_students, num_courses, num_attendance)
    print(f"students={len(db.all_people())}  courses={len(db.all_courses())}  "
        f"attendance={db.count_attendance()}  shards={len(db.engines)}")
    return db


def write_csvs():
    write_students()
    num_courses = write_courses()
    write_attendance(num_courses=num_courses)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "db"
    if mode == "csv":
        write_csvs()
    elif mode == "db":
        generate_tables(*[int(n) for n in sys.argv[2:5]])
    else:
        print("usage: python data_generetor.py [db [students courses attendance] | csv]")
