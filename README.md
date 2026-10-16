# Sharded Student Database (DBMS Project)

A small student-attendance database that spreads its data across several SQLite
files ("shards"), built with Python and SQLAlchemy.

## Tables

| Table        | Columns                                              | Where it lives                    |
|--------------|------------------------------------------------------|-----------------------------------|
| `students`   | id, name, email_id                                   | split across shards (N rows each) |
| `courses`    | id, course_name                                      | full copy on every shard          |
| `attendance` | id, class_date, student_id → students, course_id → courses, status | same shard as its student |

## How sharding works

- **Row-count sharding:** a shard holds `rows_per_shard` students; when it is
  full, the next insert opens `shard_00N+1.db`.
- **Global student ids** so attendance can reference any student.
- **Replicated lookup table:** `courses` is copied to every shard, so foreign
  keys can be checked locally.
- **Co-location:** attendance rows go to the shard that holds their student.
- Reads (`list`, `find`, `count`) fan out to every shard and merge the results.

## Run it

```
pip install -r requirements.txt
python main.py                       # interactive terminal, type 'help'
python data_generetor.py             # create tables and fill with Faker data
python data_generetor.py csv         # only write the CSV files
```

## Files

- `features.py`: ORM models and the `RowCountSharding` router
- `main.py`: interactive `db>` terminal
- `data_generetor.py`: Faker data generator (database or CSV)
