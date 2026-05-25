env "sqlalchemy" {
    url = getenv("ATLAS_DATABASE_URL")
    dev = "docker://postgres/17/dev?search_path=public"

    migration {
      dir = "file://migrations"
      revisions_schema = "atlas_schema_revisions"
    }

    schema {
        src = data.external_schema.sqlalchemy.url
    }

    format {
        migrate {
            diff = "{{ sql . \" \" }}"
        }
    }
}

data "external_schema" "sqlalchemy" {
    program = [
        "uv",
        "run",
        "-q",
        "loadModels.py",
        "postgresql"
    ]
}