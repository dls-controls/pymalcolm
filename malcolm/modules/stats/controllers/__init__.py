from .ProcessController import ProcessController,\
    parse_redirect_table

# Expose a nice namespace
from malcolm.core import submodule_all

__all__ = submodule_all(globals())