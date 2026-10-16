from pathlib import Path

from sqlalchemy import Integer, String, create_engine, func, select, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
	pass


class Person(Base):
	__tablename__ = "students"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	name: Mapped[str] = mapped_column(String(20), nullable=False)
	email_id: Mapped[str] = mapped_column(String(40), nullable=False)


class Course(Base):
	__tablename__ = "courses"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	course_name: Mapped[str] = mapped_column(String(20), nullable=False)

class Attendance(Base):
	__tablename__ = "attendance"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	class_date: Mapped[str] = mapped_column(String(20), nullable=False)
	student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
	course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
	status: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g., "Present" or "Absent"



# Routes new rows to SQLite shards using a maximum row count
class RowCountSharding:
	def __init__(self, folder: str = "shards", rows_per_shard: int = 3) -> None:
		if rows_per_shard < 1:
			raise ValueError("rows_per_shard must be at least 1")

		self.folder = Path(folder)
		self.folder.mkdir(parents=True, exist_ok=True)
		self.rows_per_shard = rows_per_shard
		self.engines = {}
		self._load_shards()

	def _load_shards(self) -> None:
		shard_files = sorted(self.folder.glob("shard_*.db"))
		shard_numbers = [int(path.stem.split("_")[1]) for path in shard_files]

		for shard_number in shard_numbers or [1]:
			self._engine_for(shard_number)

		# Student ids are global (not per shard) so attendance can reference them.
		self._next_student_id = self._max_student_id() + 1

	def _engine_for(self, shard_number: int):
		if shard_number not in self.engines:
			database = self.folder / f"shard_{shard_number:03d}.db"
			engine = create_engine(
				f"sqlite:///{database}",
				pool_size=5,
				max_overflow=10,
				pool_timeout=30,
				)
			Base.metadata.create_all(engine)
			self._copy_courses_to(engine)
			self.engines[shard_number] = engine
		return self.engines[shard_number]

	def _copy_courses_to(self, engine) -> None:
		# courses is a small lookup table, so every shard keeps a full copy
		if not self.engines:
			return
		with Session(self.engines[min(self.engines)]) as session:
			rows = [Course(id=c.id, course_name=c.course_name)
				for c in session.scalars(select(Course)).all()]
		with Session(engine) as session:
			if session.scalar(select(func.count()).select_from(Course)) == 0:
				session.add_all(rows)
				session.commit()

	def _max_student_id(self) -> int:
		highest = 0
		for engine in self.engines.values():
			with Session(engine) as session:
				highest = max(highest, session.scalar(select(func.max(Person.id))) or 0)
		return highest

	def _shard_for_insert(self) -> int:
		current_shard = max(self.engines)
		engine = self._engine_for(current_shard)

		with Session(engine) as session:
			row_count = session.scalar(select(func.count()).select_from(Person))

		if row_count >= self.rows_per_shard:
			current_shard += 1
			self._engine_for(current_shard)

		return current_shard

	def add_person(self, name: str, email_id: str) -> Person:
		shard_number = self._shard_for_insert()
		person = Person(id=self._next_student_id, name=name, email_id=email_id)

		with Session(self._engine_for(shard_number)) as session:
			session.add(person)
			session.commit()
			session.refresh(person)
		self._next_student_id += 1

		print(f"Inserted {person.name} into shard {shard_number}")
		return person

	def all_people(self) -> list[tuple[int, Person]]:
		people = []
		for shard_number, engine in sorted(self.engines.items()):
			with Session(engine) as session:
				rows = session.scalars(select(Person).order_by(Person.id)).all()
				people.extend((shard_number, person) for person in rows)
		return people

	def count_people(self) -> int:
		total = 0
		for engine in self.engines.values():
			with Session(engine) as session:
				total += session.scalar(select(func.count()).select_from(Person))
		return total

	def find_people(self, term: str) -> list[tuple[int, Person]]:
		people = []
		pattern = f"%{term}%"
		for shard_number, engine in sorted(self.engines.items()):
			with Session(engine) as session:
				rows = session.scalars(
					select(Person)
					.where(Person.name.ilike(pattern) | Person.email_id.ilike(pattern))
					.order_by(Person.id)
				).all()
				people.extend((shard_number, person) for person in rows)
		return people

	# ---- courses (replicated to every shard) ----

	def add_course(self, course_name: str) -> Course:
		with Session(self.engines[min(self.engines)]) as session:
			course_id = (session.scalar(select(func.max(Course.id))) or 0) + 1

		for engine in self.engines.values():
			with Session(engine) as session:
				session.add(Course(id=course_id, course_name=course_name))
				session.commit()

		print(f"Inserted course {course_name} (id={course_id}) into all shards")
		return Course(id=course_id, course_name=course_name)

	def all_courses(self) -> list[Course]:
		with Session(self.engines[min(self.engines)]) as session:
			return session.scalars(select(Course).order_by(Course.id)).all()

	# ---- attendance (stored on the same shard as its student) ----

	def _shard_for_student(self, student_id: int) -> int | None:
		# Students fill shards in id order, so try the computed shard first.
		guess = (student_id - 1) // self.rows_per_shard + 1
		candidates = [guess] + [n for n in sorted(self.engines) if n != guess]
		for shard_number in candidates:
			if shard_number not in self.engines:
				continue
			with Session(self.engines[shard_number]) as session:
				if session.get(Person, student_id) is not None:
					return shard_number
		return None

	def add_attendance(self, student_id: int, course_id: int, class_date: str,
			status: str) -> Attendance:
		if status not in ("Present", "Absent"):
			raise ValueError("status must be 'Present' or 'Absent'")
		shard_number = self._shard_for_student(student_id)
		if shard_number is None:
			raise ValueError(f"no student with id {student_id}")

		with Session(self.engines[shard_number]) as session:
			if session.get(Course, course_id) is None:
				raise ValueError(f"no course with id {course_id}")
			record = Attendance(class_date=class_date, student_id=student_id,
				course_id=course_id, status=status)
			session.add(record)
			session.commit()
			session.refresh(record)
		return record

	def all_attendance(self, student_id: int | None = None) -> list[tuple[int, Attendance]]:
		records = []
		for shard_number, engine in sorted(self.engines.items()):
			with Session(engine) as session:
				query = select(Attendance).order_by(Attendance.class_date, Attendance.id)
				if student_id is not None:
					query = query.where(Attendance.student_id == student_id)
				records.extend((shard_number, r) for r in session.scalars(query).all())
		return records

	def count_attendance(self) -> int:
		total = 0
		for engine in self.engines.values():
			with Session(engine) as session:
				total += session.scalar(select(func.count()).select_from(Attendance))
		return total


if __name__ == "__main__":
	from faker import Faker

	faker = Faker()
	database = RowCountSharding(rows_per_shard=3)

	for _ in range(8):
		database.add_person(faker.name(), faker.email())

	print("\nAll people:")
	for shard_number, person in database.all_people():
		print(f"shard={shard_number}, id={person.id}, name={person.name}, email={person.email_id}")