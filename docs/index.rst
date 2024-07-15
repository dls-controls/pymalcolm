Malcolm
=======

Malcolm is a middlelayer framework that implements high level configure/run
behaviour of control system components like those used in continuous scans.
This `repository`_ contains a Python implementation (pymalcolm) allowing the
creation of Malcolm servers and clients. There is also a `malcolmjs`_
JavaScript client and a Java client in `GDA`_.

Malcolm was created as part of the `Mapping project`_ at `Diamond Light Source`_
in order to improve the performance of continuous scanning, providing a system
that could scan arbitrary trajectories like spirals and grids within polygonal
regions.

What can Malcolm do?
--------------------

Malcolm provides a layer on top of `EPICS`_ that wraps up groups of `PVs`_ and
presents a higher level scanning interface to `GDA`_ via `pvAccess`_.

.. digraph:: malcolm_dls_usage

    bgcolor=transparent
    node [fontname=Arial fontsize=10 shape=box style=filled fillcolor="#8BC4E9"]
    edge [fontname=Arial fontsize=10 arrowhead=vee]

    {rank=same;Detector EPICS "HDF File"}

    Malcolm [shape=doublecircle]

    GDA -> Malcolm [label="scan.configure()\nscan.run()"]
    Malcolm -> EPICS [label="caput\ncamonitor"]
    Detector -> EPICS [label="Frame data"]
    EPICS -> "HDF File" [label="Frame data"]
    EPICS -> "Motor Controller" [label="Motion trajectory"]


Malcolm was developed for continuous scanning and the diagram above shows
how Diamond uses it, but it can also be used in other ways:

* As a library that can be used in continuous scanning scripts without acting
  as a server
* As a webserver, exposing a web GUI for configuring the underlying hardware
  that communicates to Malcolm using `JSON`_ over `websockets`_
* As a distributed object system, using either `pvAccess`_ or `websockets`_ to
  communicate and synchronise objects between multiple Malcolm processes

How is the documentation structured?
------------------------------------

The documentation is structured into a series of `tutorials-doc` and some
general `reference-doc` documentation. End users and developers need different
documentation, so links for various categories of user are listed below:

Configuring Malcolm to work with your hardware
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Work through the `tutorials-doc` then look at the `malcolm.modules` API
documentation to see what arguments need to be passed to each object in the YAML
file.

Controlling Malcolm via comms protocols
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Read the `hello_tutorial`, then look at the `block_structure` and
`message_structure` sections. The `malcolm.modules.pva` module contains some
pvAccess specific documentation. The `RunnableStates` statemachine will also
be of interest.


.. _installation_guide:

Installation Guide
------------------

Using pipenv
~~~~~~~~~~~~

We now use pipenv_ to generate the environment for Malcolm at Diamond. This
should also work in any environment where pipenv is available.

.. _pipenv: https://www.python.org/dev/peps/pep-0440

First download the source code::

    $ git clone https://github.com/DiamondLightSource/pymalcolm.git
    $ cd pymalcolm

To be able to use Malcolm run::

    $ pipenv install

For development you will need additional development packages::

    $ pipenv install --dev

Then you can use the entry point to run Malcolm::

    $ pipenv run imalcolm

Note: Malcolm is now installed as an editable module by default to make
development easier.

Using pip
~~~~~~~~~

Otherwise you can install Malcolm using pip in any venv::

    $ pip install malcolm

Which then gives you the entry point (assuming the venv is activated)::

    $ imalcolm


.. _repository:
    https://github.com/DiamondLightSource/pymalcolm

.. _malcolmjs:
    https://github.com/DiamondLightSource/malcolmjs

.. _Mapping project:
    https://indico.esss.lu.se/event/357/session/8/contribution/63


