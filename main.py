"""Interactive terminal for querying the sharded student database.

Run with:  python main.py
Type 'help' once inside for the list of commands.
"""

import csv
import shlex
from datetime import date

from data_generetor import seed_database
from features import RowCountSharding


BANNER = """
=============================================
  Sharded Student DB  -  interactive terminal
  Type 'help' for commands, 'exit' to quit.
=============================================
"""


def print_people(people) -> None:
	if not people:
		print("  (no matching rows)")
		return
	print(f"  {'shard':<6}{'id':<5}{'name':<25}{'email'}")
	print(f"  {'-' * 6}{'-' * 5}{'-' * 25}{'-' * 20}")
	for shard_number, person in people:
		print(f"  {shard_number:<6}{person.id:<5}{person.name:<25}{person.email_id}")


def print_courses(courses) -> None:
	if not courses:
		print("  (no courses)")
		return
	print(f"  {'id':<5}{'course_name'}")
	print(f"  {'-' * 5}{'-' * 25}")
	for course in courses:
		print(f"  {course.id:<5}{course.course_name}")


def print_attendance(records) -> None:
	if not records:
		print("  (no matching rows)")
		return
	print(f"  {'shard':<6}{'id':<6}{'date':<12}{'student':<9}{'course':<8}{'status'}")
	print(f"  {'-' * 6}{'-' * 6}{'-' * 12}{'-' * 9}{'-' * 8}{'-' * 7}")
	for shard_number, r in records:
		print(f"  {shard_number:<6}{r.id:<6}{r.class_date:<12}{r.student_id:<9}{r.course_id:<8}{r.status}")


def cmd_help() -> None:
	print("""
Commands:
  add <name> <email>     Insert a person (quote names with spaces: add "John Doe" j@x.com)
  list                   Show every person across all shards
  find <text>            Search name/email for <text> (case-insensitive)
  count                  Total number of people
  shards                 Show shard files and rows-per-shard
  load <file> [n]        Bulk-insert from a CSV (id,name,email_id); optional first n rows
  courses                Show every course
  addcourse <name>       Insert a course (copied to every shard)
  attend <student_id> <course_id> <Present|Absent> [YYYY-MM-DD]
                         Record attendance (date defaults to today)
  attendance [student_id]  Show attendance, optionally for one student
  seed [s] [c] [a]       Fill all 3 tables with Faker data
                         (default: 20 students, 5 courses, 50 attendance rows)
  help                   Show this message
  exit / quit            Leave the terminal
""")


def cmd_add(db, args) -> None:
	if len(args) != 2:
		print('  usage: add <name> <email>   (quote names with spaces)')
		return
	name, email = args
	db.add_person(name, email)


def cmd_find(db, args) -> None:
	if not args:
		print("  usage: find <text>")
		return
	print_people(db.find_people(" ".join(args)))


def cmd_shards(db) -> None:
	print(f"  rows_per_shard = {db.rows_per_shard}")
	print(f"  active shards  = {len(db.engines)}")
	for shard_number in sorted(db.engines):
		print(f"    shard {shard_number:03d} -> {db.folder / f'shard_{shard_number:03d}.db'}")


def cmd_load(db, args) -> None:
	if not args:
		print("  usage: load <file> [n]")
		return
	path = args[0]
	limit = int(args[1]) if len(args) > 1 else None
	try:
		with open(path, newline="") as f:
			reader = csv.DictReader(f)
			inserted = 0
			for row in reader:
				if limit is not None and inserted >= limit:
					break
				db.add_person(row["name"], row["email_id"])
				inserted += 1
	except FileNotFoundError:
		print(f"  file not found: {path}")
		return
	except KeyError:
		print("  CSV must have 'name' and 'email_id' columns")
		return
	print(f"  loaded {inserted} rows from {path}")


def cmd_addcourse(db, args) -> None:
	if not args:
		print("  usage: addcourse <name>")
		return
	db.add_course(" ".join(args))


def cmd_attend(db, args) -> None:
	if len(args) not in (3, 4):
		print("  usage: attend <student_id> <course_id> <Present|Absent> [YYYY-MM-DD]")
		return
	try:
		student_id, course_id = int(args[0]), int(args[1])
		class_date = args[3] if len(args) == 4 else date.today().isoformat()
		date.fromisoformat(class_date)
		record = db.add_attendance(student_id, course_id, class_date, args[2].capitalize())
	except ValueError as exc:
		print(f"  error: {exc}")
		return
	print(f"  recorded attendance id={record.id}")


def cmd_attendance(db, args) -> None:
	try:
		student_id = int(args[0]) if args else None
	except ValueError:
		print("  usage: attendance [student_id]")
		return
	print_attendance(db.all_attendance(student_id))


def cmd_seed(db, args) -> None:
	try:
		counts = [int(a) for a in args[:3]]
	except ValueError:
		print("  usage: seed [students] [courses] [attendance]")
		return
	seed_database(db, *counts)


def main() -> None:
	db = RowCountSharding(rows_per_shard=3)
	print(BANNER)

	while True:
		try:
			raw = input("db> ").strip()
		except (EOFError, KeyboardInterrupt):
			print()
			break

		if not raw:
			continue

		try:
			parts = shlex.split(raw)
		except ValueError as exc:
			print(f"  parse error: {exc}")
			continue

		command, args = parts[0].lower(), parts[1:]

		if command in ("exit", "quit"):
			break
		elif command == "help":
			cmd_help()
		elif command == "add":
			cmd_add(db, args)
		elif command == "list":
			print_people(db.all_people())
		elif command == "find":
			cmd_find(db, args)
		elif command == "count":
			print(f"  total people = {db.count_people()}")
		elif command == "shards":
			cmd_shards(db)
		elif command == "load":
			cmd_load(db, args)
		elif command == "courses":
			print_courses(db.all_courses())
		elif command == "addcourse":
			cmd_addcourse(db, args)
		elif command == "attend":
			cmd_attend(db, args)
		elif command == "attendance":
			cmd_attendance(db, args)
		elif command == "seed":
			cmd_seed(db, args)
		else:
			print(f"  unknown command: {command}  (try 'help')")

	print("bye.")


if __name__ == "__main__":
	main()
