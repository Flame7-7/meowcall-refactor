import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from atlas_provider_sqlalchemy.ddl import dump_ddl
from models import Base  # type: ignore

if __name__ == "__main__":
    dialect = sys.argv[1] if len(sys.argv) > 1 else "postgres"
    dump_ddl(dialect, [Base.metadata], [])
