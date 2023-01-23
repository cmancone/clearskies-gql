from clearskies.column_types import build_column_config
from .connection import Connection
def connection(name, **kwargs):
    return build_column_config(name, Connection, **kwargs)
