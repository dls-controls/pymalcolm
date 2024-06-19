Change Log
==========
All notable changes to this project will be documented in this file.
This project adheres to `Semantic Versioning <http://semver.org/>`_ after 2-1.

`6.4`_ -
-------------------
Added:

- Added functionality to send PandA Layout between Malcolm and PandA WebGui.


`6.3`_ - 2024-03-15
-------------------
Fixed:

- Changed PandA acquire RBV to avoid disarming error
- Updated CI to avoid constant failure
- Fixed patch to fully change queue to simpleQueue.

Added:

- Added Detector settable attribute to remove the position set values from the
AreaDetector XML. This avoids errors when running very large scans.
- Added 'min' option to time units on the PandA.
- Added Xspress Odin Support.

`6.2.1`_ - 2022-11-09
---------------------

Fixed:

- Minor changes to fix tutorials.

`6.2`_ - 2022-08-24
-------------------

Added:

- ADTucsen driver and runnable blocks.

Fixed:

- Bugfix: Resolve deadlock that caused malcolm to hang. This was caused by a deadlock
  between the logging thread and the cothread thread.
- Disallow pausing in PostRun state. This results in malcolm attempting to recapture
  the last point in the map, which leads to the brick going into "CS Error:
  Insufficient calculation time", because the path generated seems to backtrack.
- doublebuffer: If Prescale was set to a non-zero value on one of the sequencer
  tables it would cause timing problems in scans using the seqTriggerPart.
  This fix sets Prescale to zero during configure and logs a warning in the
  malcolm readback.

`6.1`_ - 2022-05-31
-------------------

Fixed:

- template_double_seq_pcomp: Fixed a bug in the standard design that allowed
  an extra trigger to be sent to detectors in stack scans. A logical AND
  was added to the Live Frame and Dead Frame LUT blocks from the Seq Enable
  SRGATE. **Existing scan designs should be updated with this change too.**

  .. code-block::

    "LUT4": {
      "label": "Live Frame",
      ...
      "inpc": "SRGATE2.OUT",
      ...
      "func": "(A|B)&C",
      ...
    },
- PmacChildPart: a generator with a very small move on one axis could result
  in infinity or NaN when calculating the profile points during turnarounds,
  especially for non-continuous scans. Very small distances <= 1e-12 are now
  rounded to zero.
- HdfWriterPart: removed auto_ndattr_default tag when generating XML layout
  as it doesn't conform to ADCore schema.

Added:

- PmacChildPart now checks the move to start ramp and tail off ramp against
  the soft limits of the axes and raises an Exception if the check fails.
  The move to start is checked during Configure and the tail off can be
  checked during Configure or Run, depending on the size of the trajectory.

`6.0`_ - 2022-05-11
-------------------

Changed:

- DetectorDriverPart now has a multiple image mode argument for drivers which
  use other terms for acquiring multiple images in a single acquisition.
- Malcolm no longer initialises a git repository or performs commits when
  launching the process or saving designs. Instead, it is now expected to
  handle the version control of the designs in the config_dir directory
  manually. Keeping the designs in the same repository as the top-level YAML
  file will also make it easier to maintain compatibility when rolling
  forward/back.

Fixed:

- ExposureDeadTimePart: removed config_tag from readout time and frequency
  accuracy to prevent values being saved to design, causing an error when
  trying to load them after.
- ReframePluginPart: fixed setup for scanning with outer axes

Added:

- ADAndor3 driver and runnable blocks.

`5.4`_ - 2022-03-30
-------------------

Changed:

- Removed rank padding on secondary and attribute datasets. Before this change,
  AreaDetector drivers using the HDF5 file writer would pad these data with an
  additional 1x1 dimension on top of the scan shape. This makes it simpler for
  plotting and visualisation. This change requires a minimum ADCore version of
  3.12 for the HDF5 file writing plugins.

`5.3`_ - 2022-03-18
-------------------

Changed:

- Implemented Double Buffering, using both Sequencer tables available on the PandA
  to be able to scan over the 2000 max number of rows, and to decrease the
  configuration time for long scans.

  See the updated "template_double_seq_pcomp" for the new recommended
  design. It is also recommended to set repeats on both of the SEQ tables to be
  '1', although the PandASeqTriggerPart does also set this when it is needed.

  This has a **breaking change** for old PandA designs as seqReset now has to be
  exported. Otherwise Stack scans where each inner scan is small enough that the
  points will not fill 2 SEQ tables (<8192 points or 30s per inner scan), but large
  enough that it will use more than 1 (>4096 points, 15s per inner scan) will fail.

Fixed:

- Fixed bug where, during a 3D scan, the first point of all inner scans after the
  first previously triggered immediately even if the outer axes was still moving.

`5.2`_ - 2022-01-05
-------------------

Changed:

- DetectorDriverPart's attributesFile is no longer saved in a design. This stops
  the warning when a populated Attributes to Capture table on the web GUI
  creates its own attributes file and overwrites the attributeFile value saved
  in the design (if present). If wanting to capture additional NDAttributes you
  can now either use the Attributes to Capture table and save it to your design,
  or alternatively create the attributes XML file via iocbuilder and set the
  attributes filepath at IOC startup.

Fixed:

- Fixed bug with PmacChildPart when performing large scans with start of row
  triggering. If the profile generation completed with more than 4,000 points
  to upload, then during Run you would encounter an error "Why do we still have
  points?". This is because the logic expected the profile to be able to written
  in a single write (i.e. under 2000 points). Now multiple profile writes are
  allowed when the brick is not providing a trigger at every point.

`5.1`_ - 2021-12-16
-------------------

Changed:

- PmacChildPart's profile generation is now split into two methods based on the
  trigger type. The loop performance has been improved, reducing configure
  times by ~20% for small scans and ~40% for large scans when profile point
  generation dominates. A Yield has also been added so the thread suspends
  after each batch so it doesn't block other threads for the entire profile
  calculation, which previously caused timeout problems with other components.
- HDFWriterPart now looks at the number of frames written to the HDF5 file to
  track progress and check for stalling issues. This means a scan will now fail
  instead of succeed if the file plugin receives all frames but doesn't write
  them.

Fixed:

- PmacChildPart now only reports progress if the brick is providing a trigger
  at every point. This means the scan block's RunnableController should now
  report more useful progress for scans using start of row triggering or
  position compare.

`5.0`_ - 2021-11-30
-------------------

Changed:

- BeamSelectorPart now supports holding at each position for different lengths
  of time based on a mutator modifying delay_after, allowing different exposures
  to be used for each detector.
- ExposureDeadTimePart now has fixed values for readout time and frequency
  accuracy. These are configurable in the YAML but are then fixed at runtime.
  This fixes a bug in validate where the resulting exposure time is different if
  the target design is not loaded before you run validate/configure.
  
  Designs for detector runnable blocks which contain these entries should be
  removed (remove the following lines from the JSON design files):

  .. code-block::

    - "readoutTime": 0.005,
    - "frequencyAccuracy": 50.0

  You can then set the readout time when you instantiate the runnable block
  (frequency accuracy is probably fine at the default value of 50.0):

  .. code-block:: yaml

    - ADPco.blocks.pco_runnable_block:
      mri_prefix: BL11K-ML-PCO-01
      pv_prefix: BL11K-EA-PCO-01
      config_dir: $(config_dir)
      windows_drive: G
      path_prefix: /dls
      readout_time: 0.005

Added:

- DetectorDriverPart now has optional min_acquire_period argument. When set to a
  non-zero value this is checked during validation against the generator
  duration to ensure the detector can keep up during the acquisition.
- Calculate generator duration automatically. If a duration of 0.0 is given
  then some parts will attempt to calculate a duration based on other parameters
  combined with other information they have. The parts which tweak duration are:

  - PmacChildPart
  - PandAPulseTriggerPart
  - DetectorDriverPart
  - ExposureDeadtimePart
  - AndorDriverPart
  - ReframePluginPart
  - BeamSelectorPart (based on a fixed move time)

  The largest tweak to generator duration by any part will win, and then all
  parts will validate with the new duration to check they are happy with the
  tweaked value. This can happen iteratively with up to 10 attempts per
  RunnableController.

Fixed

- Malcolm designs will no longer overwrite XMAP energy values
- The PreRunHook will now run at the beginning of do_run() so that it also runs
  on a resume.

`4.6`_ - 2021-08-17
-------------------

Changed:

- Added Unrolling block to be able to enable/disable unrolling part in scan
  design

Fixed:

- Servo interrupt frequency getter for PowerPMAC (needed at scan
  configuring phase), this requires pmac version 2-5-5 or higher
- Issue with PositionLabellerPart subscription not adding more positions after
  the initial 5000 points
- OdinWriterPart cast data type to lower case for NumPy V1.2
- Nexus templates for Savu Kinematics added to package data
- Savu Kinematics now supports no axes to move
- Scans with breakpoints and pausing are now working again after breaking in
  the 4.5 release

`4.5`_ - 2021-04-27
--------------------------

Changed:

- Improvements when scanning with software outer axes:

  - Hardware-triggered detectors remain armed between inner scans
  - By default detectors write to single files for the whole scan instead of
    for each inner scan
  - For ADOdin you can set frames per block and blocks per file to control
    number of output files

Fixed:

- Tutorials now described using pipenv
- /tmp no longer becomes a git repository when running tests
- Template designs now included in package data
- Fixed issue where existing block wiring would not be shown before a design is
  loaded

`4.4`_ - 2021-03-02
-------------------

Added:

- ADEthercat support - two runnable blocks for hardware and software-triggered
  devices
- Breakpoints - these can be defined for the scan to be broken up into
  multiple sections where run returns in an armed state
- GitHub Actions CI
- Directory monitor support - checks whether all expected file mounts are
  present on a server during configure

Fixed:

- GitLab CI script

Removed:

- Travis CI

`4-3-1`_ - 2020-09-18
---------------------

Added:

- Converted module to Python 3

  - Converted type hint comments to Python 3 annotations
  - Now use setup.cfg
  - Converted code base style using Black
  - Removed Python 2 compatibility methods
- Created Pipfile for use with pipenv
- Added mypy, Black and Flake8 checks to Travis
- Added Gitlab CI script
- Added check during configure for valid layout file for HDFWriterPart
- Added KinematicsSavuPart
- Added ADPcoWin support
- Added ffmpeg viewer as block in ADCore

Fixed:

- Fix hang when calling unsubscribe in callback


`4-2b8`_ - 2020-04-17
---------------------

- Fix for 'sharksfin issue' - start positions in trajectories were
  incorrect for high acceleration motors
- Fix for sparse trajectories accumlating errors - rename the velocity modes
  as follows and use mode 2 at the end of each sparse row

  - 0 = Average Previous to Next
  - 1 = Real Previous to Current
  - 2 = Average Previous to Current (replaces Average Current to Next)
  - 3 = Zero Velocity
- Recommend V3 of the pmac Trajectory Program but allow V2 (using V2 will
  invalidate the fix above which only applies to long, sparse trajectories)

`4-2b6`_ - 2020-02-10
---------------------

- Added NDArrayAddress CAPart to NDPlugin parts

`4-2b5`_ - 2020-01-27
---------------------

Added:

- Added builtin.defines.tmp_dir and use it in tutorials
- Web GUI now has editable meter and table row seek
- Added +DELAY badge to PandA

Fixed:

- Updated docs for training course
- Added BeamSelectorPart for DIAD

`4-2b4`_ - 2019-12-04
---------------------

Added:

- configure() now returns validated parameters rather than nothing


`4-2b3`_ - 2019-11-28
---------------------

Fixed:

- pmac now makes sparse points when doing PCOMP (previously it only did this on
  start of row triggering)
- Improve git logging of saved names
- Expose axis setpoint datasets on a per-file basis


`4-2b2`_ - 2019-11-27
---------------------

Fixed:

- PandASeqTriggerPart now reconfigures on seek to work with 3D scans
- PandA Blocks with HEALTH don't cause an error


`4-2b1`_ - 2019-11-27
---------------------

Changed:

- Scanpointgenerator bumped to 3.0.0. Adds post_delay attribute to
  CompoundGenerator
- Add enable column to Detector Table
- PMAC module now calculates more efficient turnaround points, only placing
  PVT points where acceleration changes. This requires pmac module version
  2-4-14 or later, which includes a new version of the trajectory scan program
- Versioning now taken from git describe

Added:

- System Block to hold comms modules and supporting IOCs that can be
  extracted from the DLS redirector
- Profiling web server contains link to its profiles page
- AttributePreRunPart to allow shutters to be opened and closed around runs
- Added SysLog JSON logger which will be forwarded to Graylog
- PandAPulseTriggerPart to multiply out triggers for detectors

Fixed:

- Clear dataset table on reset()
- Fixed restful server support
- Bugfixes for malcolmjs (widget:meter, navbar, colours) bumping release to
  1.7.8


`4-1-1`_ - 2019-11-18
---------------------

Fixed:

- Faulty detectors marked as such at startup, and only fail the scan they are in
  if they are used (visible and configured in Detector Table)
- Fix Odin dataset names passed via the Dataset Table


`4-1`_ - 2019-09-26
-------------------

Fixed:

- Increased xml generation performance of position labeller
- Bugfixes for malcolmjs, bumping release from 1.7.1 -> 1.7.4

Changed:

- panda_pcomp is now panda_seq_trigger
- Bump dependency on scanpointgenerator to 2.3
- Mark scans as stalled if detector doesn't produce frames for more than 60s

Added:

- maxVelocityPercent added to motors. Allows turnaround times to be tweaked
  without changing VMAX
- axisNumber attribute to pmac motors
- UnrollingPart to allow Odin detectors to squash scan dimensions together
  to avoid unperformant VDS snake scans
- Some new icons for PandA
- PMAC now generates sparse points for lines when not being asked to trigger
- Preliminary Detector Table support to allow disabling detectors at configure()


`4-0`_ - 2019-07-05
-------------------

Added:

- PMAC Row Gate only trigger option for use with PandASeqTriggerPart
- PandA tutorial

Fixed:

- Now works with Python3.7
- ADCore HDF Writer now always writes at least some Attributes


`4-0b2`_ - 2019-06-20
---------------------

Changed:

- All PV arguments are now pv_prefix, not prefix

Added:

- PMAC Tutorial
- Live and Dead frame template for PandA


`4-0b1`_ - 2019-05-03
---------------------

Changed:

- CS and motors now show a link to parent PMAC, require pmac version 2-2
- Added Position Compare support for PandA via 2 SEQ blocks
- State machine. Added Finished state and Malcolm will now sit in Finished state
  after a scan
- CSMove changed to explicitly tell the motor controller how long it should take
  to do the move to start
- Changed seeking to not allow it to stop on a configured_step boundary
- Disable checking of scanpointgenerator units while GDA doesn't send the right
  ones
- PMAC should now be a ManagerController, with PmacChildPart in the scan
- PandA now specifies datasets in a Bits and Positions table
- Web GUI now takes last run parameters from server for methods
- All identifiers in YAML must now be in snake_case

Added:

- Make use of FlushNow in ADCore, which flushes data and attributes after every
  second during run() or when commanded through the record on HDF Writer. Files
  are kept open until next reset()/abort()

Fixed:

- caactionpart now waits for good status, prevents timeout errors when doing
  caputs

Added:

- ADEiger support
- Improved ADAndor support with knowledge of frame transfer mode

Fixed:

- Race condition on making async logging at imalcolm startup


`3-5-1`_ - 2019-07-26
---------------------

Fixed:

- Added timeout if detector doesn't produce frames for 120 seconds


`3-5`_ - 2019-06-17
-------------------

Changed:

- Removed local file logging
- Add pymalcolm version tag to Block meta
- Support no axis scans in PMAC. Requires pmac xxxx
- Do as many scanpointgenerator dimensions as possible to support acquire scans

`3-4-1`_ - 2019-05-08
---------------------

Fixed:

- no_save now saves everything apart from what is passed. Previously it was
  updating a set that was common to all ChildPart subclasses
- pmactrajectorypart no longer checks CS numbers on validate in case they are
  different to what is saved


`3-4`_ - 2019-03-28
-------------------

Added:

- ADOdin VDS and nexus file generation
- HDF Attributes control of NDAttributes written
- Windows detector file path support
- added precision and units to number attributes

Fixed:

- Update to malcolmjs 1.6.2 to fix cryptic errors


`3-3`_ - 2019-02-19
-------------------

Added:

- Precision and units in a display_t for NumberMeta
- Number of frames per chunk in HDF writer Block saved
- Merlin support
- Waveform Table support with plot widget in malcolmjs

Fixed:

- Disconnected PVs now keep their value, rather than zeroing it
- Update malcolmjs to 1.6.1
- Subtle bug with turnaround trajectories at high accelerations
- Made explicit the attributes that are managed by ChildPart and shouldn't save
- save() now calls sync so file is flushed to disk (for PandA)


`3-2`_ - 2019-01-21
-------------------

Added:

- ADOdin support for start/stop (not rewind or VDS yet)
- Configurable poll period of PandA

Fixed:

- Performance tweaks for PandA web control, which makes time_t unordered dict
- Better error message for wrong cs_port in a trajectory scan


`3-0`_ - 2019-01-04
-------------------

Changed:

- areaDetectors now set acquirePeriod = exposure + readout_time
- Andor calculates readout_time from the reported driver values

Added:

- soft_trigger_modes to DetectorDriverPart to calculate is_hardware_triggered

Fixed:

- Look at operstart rather than flags to see if link is down for WebSockets
- BrickPart can now take initial_visibility again (broken in 3-0b2)
- Add git username and email settings at save for git versions that support it


`3-0b2`_ - 2018-12-05
---------------------

Added:

- PYMALCOLM_STACK_SIZE environment variable setting coroutine stack size
- Default is still 0 (coroutines share stack)
- DetectorDriverPart now also writes acqurirePeriod if writing exposure

Fixed:

- ADAndor now uses imageMode=Multiple not Fixed
- ADAndor now uses standard DetectorDriverPart


`3-0b1`_ - 2018-12-04
---------------------

Fixed:

- Trajectory scan back to level driven pulses as 24V GPIO has soft falling edges
- Update malcolmjs to 1.5.1


`3-0a9`_ - 2018-12-03
---------------------

Fixed:

- Websocket only validates for interfaces that are up
- Motor records have a number of records read only if they don't need writing


`3-0a8`_ - 2018-11-30
---------------------

Changed:

- Websocket server now blocks write access from outside subnet

Fixed:

- PandA now reports correct datasets to the HDF writer to link
- ADAndor does exposure time in a more standard way


`3-0a7`_ - 2018-11-27
---------------------

Changed:

- cothread is now a required dependency

Fixed:

- Updated first 3 tutorials to match Malcolm3 changes
- Bug on saving a new design after loading design=""

Updated:

- Web gui version (malcolmjs 1.5)


`3-0a6`_ - 2018-11-05
---------------------

Fixed:

- p4p imalcolm packaging and >= handling
- Some documentation updates


`3-0a5`_ - 2018-10-17
---------------------

Changed:

- Web gui version (malcolmjs 1.3.1)

Fixed:

- Minor bug with loading non-existant attributes failing
- Some internal issues in p4p pvAccess support
- ProxyController refactor, moving some code to ClientComms


`3-0a4`_ - 2018-09-24
---------------------

Added:

- Web gui (malcolmjs 1.1.0)

Changed:

- PVAccess library from pvaPy to p4p. This means that monitor deltas and RPC
  errors now work as expected

Fixed:

- PMAC trajectory pause waits for long enough to get GPIO signals
- MotorInfo.make_velocity_profile now works with small distances, zero
  velocities, and a min_time. A floating point rounding error was previously
  making it return less than min_time
- Make all areaDetectors wait on stop() for the acquire light to go out
- Updated DEFAULT_TIMEOUT to 10s
- Fixed pmac so that stretched pulses on a PROFILE_POINTS boundary work
- Added pollNow() for pmac GPIOs (requires pmac 2-1 or later)
- Enforce camelCaseFields and Alphanumeric + underscore + dash Part names
- Don't load child runnable block designs at init
- Error message when a Field is not writeable now shows current state
- Check generator units match axis units in pmac cs part
- Added "get" option to Put to allow current value to be returned
- out/inports are now source/sinkPorts
- Added widget:tree and widget:multilinetextupdate and removed widget:title
- rbv_suff is now rbv_suffix


`3-0a3`_ - 2018-07-25
---------------------

Fixed:

- PMAC move to start uses the right timeout (instead of fixed 5 seconds)
- SimultaneousAxes now works from axesToMove instead of generator axes


`3-0a2`_ - 2018-07-17
---------------------

Fixed:

- DLS specific require paths


`3-0a1`_ - 2018-07-16
---------------------

Changed:

- All yaml keys are snake_case rather than camelCase
- Default webserver port is now 8008
- axesToMove attribute has changed to simultaneousAxes
- Load save more explicit with initial_visibility on ChildParts
- Python classes now use `annotypes`_ for type introspection
- Hook decorators are replaced by a more explicit Part.register_hooked()
- DetectorDriverPart refactored to give a better interface


`2-3-1`_ - 2018-06-07
---------------------

Fixed:

- Graylog config for DLS logging to point to graylog2


`2-3`_ - 2018-05-31
-------------------

Added:

- event_timeout to future waiting functions

Fixed:

- HDF writer only waits up to 60s for new frames to tick before timing out
- Make hardware step scanning work


`2-2`_ - 2018-03-29
-------------------

Changed:

- Split arrayCounter into arrayCounter and arrayCounterReadback on ADCore ndarraybase_parts

Fixed:

- Made RunnableChildPart handle a resume on a child that was Armed not Paused
- Made VDS depend on h5py 2.7.1 and vds-gen 0.2
- Removed flaky sum datasets of VDS
- Fix a regression where Xmap would not report its DET and sum datasets

Added:

- dtacq support


`2-1`_ - 2017-08-30
-------------------
Changed:

- Major refactor, many breaking changes


`2-0a6`_ - 2016-10-03
---------------------
Changed:

- Attributes no longer serialize to NTAttribute, they now use NTScalar,
  NTScalarArray, NTTable or NTUnion


`2-0a5`_ - 2016-10-03
---------------------
Added:

- Support for PandABox

Fixed:

- Extra padding point in turnaround in PMACTrajectoryScan


`2-0a4`_ - 2016-09-20
---------------------
Added:

- PMAC trajectory scanning
- Pause, Abort and Rewind
- PVA: Get and Post for client


`2-0a3`_ - 2016-08-31
---------------------
Added:

- imalcolm client script


`2-0a2`_ - 2016-08-30
---------------------
Added:

- Ability to start comms from YAML
- PVAccess comms
- Dummy PMAC trajectory scan


2-0a1 - 2016-08-15
------------------
Added:

- Initial release with hello world and websocket comms

.. _6.3: https://github.com/dls-controls/pymalcolm/compare/6.2...6.3
.. _6.2.1: https://github.com/dls-controls/pymalcolm/compare/6.2...6.2.1
.. _6.2: https://github.com/dls-controls/pymalcolm/compare/6.1...6.2
.. _6.1: https://github.com/dls-controls/pymalcolm/compare/6.0...6.1
.. _6.0: https://github.com/dls-controls/pymalcolm/compare/5.4...6.0
.. _5.4: https://github.com/dls-controls/pymalcolm/compare/5.3...5.4
.. _5.3: https://github.com/dls-controls/pymalcolm/compare/5.2...5.3
.. _5.2: https://github.com/dls-controls/pymalcolm/compare/5.1...5.2
.. _5.1: https://github.com/dls-controls/pymalcolm/compare/5.0...5.1
.. _5.0: https://github.com/dls-controls/pymalcolm/compare/4.6...5.0
.. _4.6: https://github.com/dls-controls/pymalcolm/compare/4.5...4.6
.. _4.5: https://github.com/dls-controls/pymalcolm/compare/4.4...4.5
.. _4.4: https://github.com/dls-controls/pymalcolm/compare/4-3-1...4.4
.. _4-3-1: https://github.com/dls-controls/pymalcolm/compare/4-2b8...4-3-1
.. _4-2b8: https://github.com/dls-controls/pymalcolm/compare/4-2b6...4-2b8
.. _4-2b6: https://github.com/dls-controls/pymalcolm/compare/4-2b5...4-2b6
.. _4-2b5: https://github.com/dls-controls/pymalcolm/compare/4-2b4...4-2b5
.. _4-2b4: https://github.com/dls-controls/pymalcolm/compare/4-2b3...4-2b4
.. _4-2b3: https://github.com/dls-controls/pymalcolm/compare/4-2b2...4-2b3
.. _4-2b2: https://github.com/dls-controls/pymalcolm/compare/4-2b1...4-2b2
.. _4-2b1: https://github.com/dls-controls/pymalcolm/compare/4-1-1...4-2b1
.. _4-1-1: https://github.com/dls-controls/pymalcolm/compare/4-1...4-1-1
.. _4-1: https://github.com/dls-controls/pymalcolm/compare/4-0...4-1
.. _4-0: https://github.com/dls-controls/pymalcolm/compare/4-0b2...4-0
.. _4-0b2: https://github.com/dls-controls/pymalcolm/compare/4-0b1...4-0b2
.. _4-0b1: https://github.com/dls-controls/pymalcolm/compare/3-5-1...4-0b1
.. _3-5-1: https://github.com/dls-controls/pymalcolm/compare/3-5...3-5-1
.. _3-5: https://github.com/dls-controls/pymalcolm/compare/3-4-1...3-5
.. _3-4-1: https://github.com/dls-controls/pymalcolm/compare/3-4...3-4-1
.. _3-4: https://github.com/dls-controls/pymalcolm/compare/3-3...3-4
.. _3-3: https://github.com/dls-controls/pymalcolm/compare/3-2...3-3
.. _3-2: https://github.com/dls-controls/pymalcolm/compare/3-0...3-2
.. _3-0: https://github.com/dls-controls/pymalcolm/compare/3-0b2...3-0
.. _3-0b2: https://github.com/dls-controls/pymalcolm/compare/3-0b1...3-0b2
.. _3-0b1: https://github.com/dls-controls/pymalcolm/compare/3-0a9...3-0b1
.. _3-0a9: https://github.com/dls-controls/pymalcolm/compare/3-0a8...3-0a9
.. _3-0a8: https://github.com/dls-controls/pymalcolm/compare/3-0a7...3-0a8
.. _3-0a7: https://github.com/dls-controls/pymalcolm/compare/3-0a6...3-0a7
.. _3-0a6: https://github.com/dls-controls/pymalcolm/compare/3-0a5...3-0a6
.. _3-0a5: https://github.com/dls-controls/pymalcolm/compare/3-0a4...3-0a5
.. _3-0a4: https://github.com/dls-controls/pymalcolm/compare/3-0a3...3-0a4
.. _3-0a3: https://github.com/dls-controls/pymalcolm/compare/3-0a2...3-0a3
.. _3-0a2: https://github.com/dls-controls/pymalcolm/compare/3-0a1...3-0a2
.. _3-0a1: https://github.com/dls-controls/pymalcolm/compare/2-3-1...3-0a1
.. _2-3-1: https://github.com/dls-controls/pymalcolm/compare/2-3...2-3-1
.. _2-3: https://github.com/dls-controls/pymalcolm/compare/2-2...2-3
.. _2-2: https://github.com/dls-controls/pymalcolm/compare/2-1...2-2
.. _2-1: https://github.com/dls-controls/pymalcolm/compare/2-0a6...2-1
.. _2-0a6: https://github.com/dls-controls/pymalcolm/compare/2-0a5...2-0a6
.. _2-0a5: https://github.com/dls-controls/pymalcolm/compare/2-0a4...2-0a5
.. _2-0a4: https://github.com/dls-controls/pymalcolm/compare/2-0a3...2-0a4
.. _2-0a3: https://github.com/dls-controls/pymalcolm/compare/2-0a2...2-0a3
.. _2-0a2: https://github.com/dls-controls/pymalcolm/compare/2-0a1...2-0a2

.. _annotypes: https://github.com/dls-controls/annotypes
