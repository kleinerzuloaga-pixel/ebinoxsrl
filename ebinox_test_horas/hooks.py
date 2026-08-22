from odoo.exceptions import UserError

from .staging_guard import is_allowed_staging_database


def _database_name(env_or_cursor):
    cursor = getattr(env_or_cursor, "cr", env_or_cursor)
    return getattr(cursor, "dbname", "")


def pre_init_hook(env_or_cursor):
    """Fail closed: install only on Odoo.sh staging builds of this project."""
    database = _database_name(env_or_cursor)
    if not is_allowed_staging_database(database):
        raise UserError(
            "Instalación bloqueada: Ebinox - Novedades y Horas sólo puede "
            "instalarse en una base staging autorizada (ebinox-staging- y un "
            "número de build). Base recibida: %s."
            % (database or "<desconocida>")
        )
