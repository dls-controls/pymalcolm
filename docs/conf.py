# -*- coding: utf-8 -*-
#
# malcolm documentation build configuration file
import os
import sys

from enum import Enum

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..")))
sys.path.append(os.path.dirname(__file__))

import malcolm


# Autodoc event handlers
def skip_member(app, what, name, obj, skip, options):
    # Override enums to always be documented
    if isinstance(obj, Enum):
        return False


def setup(app):
    app.connect("autodoc-skip-member", skip_member)
    from generate_api_docs import generate_docs

    generate_docs()  # Generate modules_api.rst


# -- General configuration ------------------------------------------------

# General information about the project.
project = "malcolm"
copyright = "2015, Diamond Light Source"
author = "Tom Cobb"

# The short X.Y version.
version = malcolm.__version__.split("+")[0]
# The full version, including alpha/beta/rc tags.
release = malcolm.__version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.inheritance_diagram",
    "sphinx.ext.graphviz",
    "IPython.sphinxext.ipython_console_highlighting",
    "annotypes.sphinxext.call_types",
]

autoclass_content = "both"

autodoc_member_order = "bysource"

graphviz_output_format = "svg"

# If true, Sphinx will warn about all references where the target can't be found
nitpicky = True

# Both the class’ and the __init__ method’s docstring are concatenated and
# inserted into the main body of the autoclass directive
autoclass_content = "both"

# Order the members by the order they appear in the source code
autodoc_member_order = "bysource"

# Don't inherit docstrings from baseclasses
autodoc_inherit_docstrings = False

# Output graphviz directive produced images in a scalable format
graphviz_output_format = "svg"

# The name of a reST role (builtin or Sphinx extension) to use as the default
# role, that is, for text marked up `like this`
default_role = "any"

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]


# The suffix of source filenames.
source_suffix = ".rst"

# The master toctree document.
master_doc = "contents"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# These patterns also affect html_static_path and html_extra_path
exclude_patterns = ["_build"]

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

intersphinx_mapping = dict(
    python=("https://docs.python.org/3/", None),
    scanpointgenerator=("https://scanpointgenerator.readthedocs.io/en/latest/", None),
    numpy=("https://numpy.org/doc/stable", None),
    tornado=("https://www.tornadoweb.org/en/stable/", None),
    p4p=("https://mdavidsaver.github.io/p4p-dev/", None),
)

# A dictionary of graphviz graph attributes for inheritance diagrams.
inheritance_graph_attrs = dict(rankdir="TB")

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme_github_versions"

# Options for the sphinx rtd theme, use DLS blue
html_theme_options = dict(style_nav_header_background="rgb(7, 43, 93)")

# Add any paths that contain custom themes here, relative to this directory.
# html_theme_path = []

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# Custom sidebar templates, maps document names to template names.
# html_sidebars = {}

# Additional templates that should be rendered to pages, maps page names to
# template names.
# html_additional_pages = {}

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
html_show_sphinx = False

# If true, "(C) Copyright ..." is shown in the HTML footer. Default is True.
html_show_copyright = True

# Output file base name for HTML help builder.
htmlhelp_basename = "malcolmdoc"

# Logo
html_logo = "malcolm-logo.svg"
html_favicon = "malcolm-logo.ico"

# Common links that should be available on every page
rst_epilog = """
.. _Mapping project:
    https://indico.esss.lu.se/event/357/session/8/contribution/63
.. _EPICS:
    https://epics.anl.gov/
.. _PVs:
    https://docs.epics-controls.org/en/latest/specs/ca_protocol.html#process-variables
.. _GDA:
    http://www.opengda.org/
.. _pvAccess:
    http://epics-pvdata.sourceforge.net/arch.html#Network
.. _websockets:
    https://en.wikipedia.org/wiki/WebSocket
.. _Diamond Light Source:
    https://www.diamond.ac.uk/
.. _JSON:
    https://www.json.org/
.. _areaDetector:
    https://cars9.uchicago.edu/software/epics/areaDetector.html
.. _YAML:
    https://en.wikipedia.org/wiki/YAML
.. _IPython:
    https://ipython.org
.. _Scan Point Generator:
    https://scanpointgenerator.readthedocs.io
.. _NeXus:
    https://www.nexusformat.org/
.. _HDF5:
    http://portal.hdfgroup.org/display/support
"""
