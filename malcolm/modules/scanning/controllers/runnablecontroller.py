from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type

from annotypes import Anno, add_call_types, deserialize_object, json_encode
from scanpointgenerator import CompoundGenerator

from malcolm.compat import OrderedDict
from malcolm.core import (
    DEFAULT_TIMEOUT,
    AbortedError,
    AMri,
    Context,
    NumberMeta,
    Part,
    Queue,
    Table,
    TimeoutError,
    Widget,
)
from malcolm.core.models import MethodMeta, TableMeta, VMeta
from malcolm.modules import builtin

from ..hooks import (
    AAxesToMove,
    AbortHook,
    ABreakpoints,
    ConfigureHook,
    ControllerHook,
    PauseHook,
    PostConfigureHook,
    PostRunArmedHook,
    PostRunReadyHook,
    PreConfigureHook,
    PreRunHook,
    ReportStatusHook,
    RunHook,
    SeekHook,
    ValidateHook,
)
from ..infos import ConfigureParamsInfo, ParameterTweakInfo, RunProgressInfo
from ..util import AGenerator, ConfigureParams, RunnableStates

PartContextParams = Iterable[Tuple[Part, Context, Dict[str, Any]]]
PartConfigureParams = Dict[Part, ConfigureParamsInfo]

ss = RunnableStates

with Anno("The validated configure parameters"):
    AConfigureParams = ConfigureParams
with Anno("Step to mark as the last completed step, -1 for current"):
    ALastGoodStep = int

# Pull re-used annotypes into our namespace in case we are subclassed
AConfigDir = builtin.controllers.AConfigDir
AInitialDesign = builtin.controllers.AInitialDesign
ADescription = builtin.controllers.ADescription
AUseGit = builtin.controllers.AUseGit
ATemplateDesigns = builtin.controllers.ATemplateDesigns


def get_steps_per_run(generator: CompoundGenerator, axes_to_move: List[str]) -> int:
    steps = 1
    axes_set = set(axes_to_move)
    for dim in reversed(generator.dimensions):
        # If the axes_set is empty and the dimension has axes then we have done
        # as many dimensions as we can, so return
        if dim.axes and not axes_set:
            break
        # Consume the axes that this generator scans
        for axis in dim.axes:
            assert axis in axes_set, "Axis %s is not in %s" % (axis, axes_to_move)
            axes_set.remove(axis)
        # Now multiply by the dimensions to get the number of steps
        steps *= dim.size
    return steps


def update_configure_model(
    configure_model: MethodMeta, part_configure_infos: List[ConfigureParamsInfo]
) -> None:
    # These will not be inserted as they already exist

    ignored = list(ConfigureHook.call_types)

    # Re-calculate the following
    required = []
    metas = OrderedDict()
    defaults = OrderedDict()

    # First do the required arguments
    for k in configure_model.takes.required:
        required.append(k)
        metas[k] = configure_model.takes.elements[k]
    for info in part_configure_infos:
        for k in info.required:
            if k not in required + ignored:
                required.append(k)
                # TODO: moan about type changes, when != works...
                metas[k] = info.metas[k]

    # Now the default and optional
    for k in configure_model.takes.elements:
        if k not in required:
            metas[k] = configure_model.takes.elements[k]
    for info in part_configure_infos:
        for k, meta in info.metas.items():
            if k not in required + ignored:
                # TODO: moan about type changes, when != works...
                metas[k] = meta
                if k in info.defaults:
                    if isinstance(meta, TableMeta) and not min(
                        m.writeable for m in meta.elements.values()
                    ):
                        # This is a table with non-writeable rows, merge the
                        # defaults together row by row
                        rows = []
                        if k in defaults:
                            rows += defaults[k].rows()
                        rows += info.defaults[k].rows()
                        assert meta.table_cls, "No Meta table class"
                        defaults[k] = meta.table_cls.from_rows(rows)
                    else:
                        defaults[k] = info.defaults[k]

    # Copy and prepare values for takes and returns
    takes_metas = OrderedDict()
    returns_metas = OrderedDict()
    for k, v in metas.items():
        takes_metas[k] = deserialize_object(v.to_dict(), VMeta)
        returns_metas[k] = deserialize_object(v.to_dict(), VMeta)
        returns_metas[k].set_writeable(False)

    # Set them on the model
    configure_model.takes.set_elements(takes_metas)
    configure_model.takes.set_required(required)
    configure_model.returns.set_elements(returns_metas)
    configure_model.returns.set_required(required)
    configure_model.set_defaults(defaults)


def merge_non_writeable_table(
    default: Table, supplied: Table, non_writeable: List[int]
) -> Table:
    default_rows = list(default.rows())
    for supplied_row in supplied.rows():
        key = [supplied_row[i] for i in non_writeable]
        for default_row in default_rows:
            if key == [default_row[i] for i in non_writeable]:
                break
        else:
            d = OrderedDict()
            for i, k in enumerate(supplied.call_types):
                if i in non_writeable:
                    d[k] = supplied_row[i]
            raise ValueError(
                "Table row with %s doesn't match a row in the default table"
                % json_encode(d)
            )
        for i, v in enumerate(supplied_row):
            if i not in non_writeable:
                default_row[i] = v
    table = default.from_rows(default_rows)
    return table


class RunnableController(builtin.controllers.ManagerController):
    """RunnableDevice implementer that also exposes GUI for child parts"""

    # The state_set that this controller implements
    state_set = ss()

    def __init__(
        self,
        mri: AMri,
        config_dir: AConfigDir,
        template_designs: ATemplateDesigns = "",
        initial_design: AInitialDesign = "",
        use_git: AUseGit = True,
        description: ADescription = "",
    ) -> None:
        super().__init__(
            mri=mri,
            config_dir=config_dir,
            template_designs=template_designs,
            initial_design=initial_design,
            use_git=use_git,
            description=description,
        )
        # Shared contexts between Configure, Run, Pause, Seek, Resume
        self.part_contexts: Dict[Part, Context] = {}
        # Any custom ConfigureParams subclasses requested by Parts
        self.part_configure_params: PartConfigureParams = {}
        # Params passed to configure()
        self.configure_params: Optional[ConfigureParams] = None
        # Progress reporting dict of completed_steps for each part
        self.progress_updates: Optional[Dict[Part, int]] = None
        # Queue so that do_run can wait to see why it was aborted and resume if
        # needed
        self.resume_queue: Optional[Queue] = None
        # Stored for pause. If using breakpoints, it is a list of steps
        self.steps_per_run = []  # type: List[int]
        # If the list of breakpoints is not empty, this will be true
        self.use_breakpoints = False  # type: bool
        # Absolute steps where the run() returns
        self.breakpoint_steps = []  # type: List[int]
        # Breakpoint index, modified in run() and pause()
        self.breakpoint_index = 0
        # Queue so we can wait for aborts to complete
        self.abort_queue: Optional[Queue] = None
        # Create sometimes writeable attribute for the current completed scan
        # step
        self.completed_steps = NumberMeta(
            "int32",
            "Readback of number of scan steps",
            tags=[Widget.METER.tag()],  # Widget.TEXTINPUT.tag()]
        ).create_attribute_model(0)
        self.field_registry.add_attribute_model(
            "completedSteps", self.completed_steps, self.pause
        )
        self.set_writeable_in(self.completed_steps, ss.PAUSED, ss.ARMED)
        # Create read-only attribute for the number of configured scan steps
        self.configured_steps = NumberMeta(
            "int32",
            "Number of steps currently configured",
            tags=[Widget.TEXTUPDATE.tag()],
        ).create_attribute_model(0)
        self.field_registry.add_attribute_model(
            "configuredSteps", self.configured_steps
        )
        # Create read-only attribute for the total number scan steps
        self.total_steps = NumberMeta(
            "int32", "Readback of number of scan steps", tags=[Widget.TEXTUPDATE.tag()]
        ).create_attribute_model(0)
        self.field_registry.add_attribute_model("totalSteps", self.total_steps)
        # Create the method models
        self.field_registry.add_method_model(self.validate)
        self.set_writeable_in(
            self.field_registry.add_method_model(self.configure), ss.READY, ss.FINISHED
        )
        self.set_writeable_in(self.field_registry.add_method_model(self.run), ss.ARMED)
        self.set_writeable_in(
            self.field_registry.add_method_model(self.abort),
            ss.READY,
            ss.CONFIGURING,
            ss.ARMED,
            ss.RUNNING,
            ss.POSTRUN,
            ss.PAUSED,
            ss.SEEKING,
            ss.FINISHED,
        )
        self.set_writeable_in(
            self.field_registry.add_method_model(self.pause),
            ss.ARMED,
            ss.PAUSED,
            ss.RUNNING,
            ss.POSTRUN,
            ss.FINISHED,
        )
        self.set_writeable_in(
            self.field_registry.add_method_model(self.resume), ss.PAUSED
        )
        # Override reset to work from aborted too
        self.set_writeable_in(
            self.field_registry.get_field("reset"),
            ss.FAULT,
            ss.DISABLED,
            ss.ABORTED,
            ss.ARMED,
            ss.FINISHED,
        )
        # Allow Parts to report their status
        self.info_registry.add_reportable(RunProgressInfo, self.update_completed_steps)
        # Allow Parts to request extra items from configure
        self.info_registry.add_reportable(
            ConfigureParamsInfo, self.update_configure_params
        )

    def get_steps_per_run(self, generator, axes_to_move, breakpoints):
        # type: (CompoundGenerator, List[str], List[int]) -> List[int]
        self.use_breakpoints = False
        steps = [1]
        axes_set = set(axes_to_move)
        for dim in reversed(generator.dimensions):
            # If the axes_set is empty and the dimension has axes then we have
            # done as many dimensions as we can, so return
            if dim.axes and not axes_set:
                break
            # Consume the axes that this generator scans
            for axis in dim.axes:
                assert axis in axes_set, "Axis %s is not in %s" % (axis, axes_to_move)
                axes_set.remove(axis)
            # Now multiply by the dimensions to get the number of steps
            steps[0] *= dim.size

        # If we have breakpoints we make a list of steps
        if len(breakpoints) > 0:
            total_breakpoint_steps = sum(breakpoints)
            assert (
                total_breakpoint_steps <= steps[0]
            ), "Sum of breakpoints greater than steps in scan"
            self.use_breakpoints = True

            # Cast to list so we can append
            breakpoints_list = list(breakpoints)

            # Check if we need to add the final breakpoint to the inner scan
            if total_breakpoint_steps < steps[0]:
                last_breakpoint = steps[0] - total_breakpoint_steps
                breakpoints_list += [last_breakpoint]

            # Repeat the set of breakpoints for each outer step
            breakpoints_list *= self._get_outer_steps(generator, axes_to_move)

            steps = breakpoints_list

            # List of steps completed at end of each run
            self.breakpoint_steps = [sum(steps[:i]) for i in range(1, len(steps) + 1)]

        return steps

    def _get_outer_steps(self, generator, axes_to_move):
        outer_steps = 1
        for dim in reversed(generator.dimensions):
            outer_axis = True
            for axis in dim.axes:
                if axis in axes_to_move:
                    outer_axis = False
            if outer_axis:
                outer_steps *= dim.size
        return outer_steps

    def do_reset(self):
        super().do_reset()
        self.configured_steps.set_value(0)
        self.completed_steps.set_value(0)
        self.total_steps.set_value(0)
        self.breakpoint_index = 0

    def update_configure_params(
        self, part: Part = None, info: ConfigureParamsInfo = None
    ) -> None:
        """Tell controller part needs different things passed to Configure"""
        with self.changes_squashed:
            # Update the dict
            if part:
                assert info, "No info for part"
                self.part_configure_params[part] = info

            # No process yet, so don't do this yet
            if self.process is None:
                return

            # Make a list of all the infos that the parts have contributed
            part_configure_infos = []
            for part in self.parts.values():
                info = self.part_configure_params.get(part, None)
                if info:
                    part_configure_infos.append(info)

            # Update methods from the updated configure model
            for method_name in ("configure", "validate"):
                # Get the model of our configure method as the starting point
                method_meta = MethodMeta.from_callable(self.configure)
                # Update the configure model from the infos
                update_configure_model(method_meta, part_configure_infos)
                # Put the created metas onto our block meta
                method = self._block[method_name]
                method.meta.takes.set_elements(method_meta.takes.elements)
                method.meta.takes.set_required(method_meta.takes.required)
                method.meta.returns.set_elements(method_meta.returns.elements)
                method.meta.returns.set_required(method_meta.returns.required)
                method.meta.set_defaults(method_meta.defaults)
                method.set_took()
                method.set_returned()

    def update_block_endpoints(self):
        super().update_block_endpoints()
        self.update_configure_params()

    def _part_params(
        self, part_contexts: Dict[Part, Context] = None, params: ConfigureParams = None
    ) -> PartContextParams:
        if part_contexts is None:
            part_contexts = self.part_contexts
        if params is None:
            params = self.configure_params
        for part, context in part_contexts.items():
            args = {}
            assert params, "No params"
            for k in params.call_types:
                args[k] = getattr(params, k)
            yield part, context, args

    # This will be serialized, so maintain camelCase for axesToMove
    # noinspection PyPep8Naming
    @add_call_types
    def validate(
        self,
        generator: AGenerator,
        axesToMove: AAxesToMove = None,
        breakpoints: ABreakpoints = None,
        **kwargs: Any
    ) -> AConfigureParams:
        """Validate configuration parameters and return validated parameters.

        Doesn't take device state into account so can be run in any state
        """
        iterations = 10
        # We will return this, so make sure we fill in defaults
        for k, default in self._block.configure.meta.defaults.items():
            kwargs.setdefault(k, default)
        # The validated parameters we will eventually return
        params = ConfigureParams(generator, axesToMove, breakpoints, **kwargs)
        # Make some tasks just for validate
        part_contexts = self.create_part_contexts()
        # Get any status from all parts
        status_part_info = self.run_hooks(
            ReportStatusHook(p, c) for p, c in part_contexts.items()
        )
        while iterations > 0:
            # Try up to 10 times to get a valid set of parameters
            iterations -= 1
            # Validate the params with all the parts
            validate_part_info = self.run_hooks(
                ValidateHook(p, c, status_part_info, **kwargs)
                for p, c, kwargs in self._part_params(part_contexts, params)
            )
            tweaks: List[ParameterTweakInfo] = ParameterTweakInfo.filter_values(
                validate_part_info
            )
            if tweaks:
                for tweak in tweaks:
                    deserialized = self._block.configure.meta.takes.elements[
                        tweak.parameter
                    ].validate(tweak.value)
                    setattr(params, tweak.parameter, deserialized)
                    self.log.debug("Tweaking {tweak.parameter} to {deserialized}")
            else:
                # Consistent set, just return the params
                return params
        raise ValueError("Could not get a consistent set of parameters")

    def abortable_transition(self, state):
        with self._lock:
            # We might have been aborted just now, so this will fail
            # with an AbortedError if we were
            self_ctx = self.part_contexts.get(self, None)
            if self_ctx:
                self_ctx.sleep(0)
            self.transition(state)

    # This will be serialized, so maintain camelCase for axesToMove
    # noinspection PyPep8Naming
    @add_call_types
    def configure(
        self,
        generator: AGenerator,
        axesToMove: AAxesToMove = None,
        breakpoints: ABreakpoints = None,
        **kwargs: Any
    ) -> AConfigureParams:
        """Validate the params then configure the device ready for run().

        Try to prepare the device as much as possible so that run() is quick to
        start, this may involve potentially long running activities like moving
        motors.

        Normally it will return in Armed state. If the user aborts then it will
        return in Aborted state. If something goes wrong it will return in Fault
        state. If the user disables then it will return in Disabled state.
        """
        params = self.validate(generator, axesToMove, breakpoints, **kwargs)
        state = self.state.value
        try:
            self.transition(ss.CONFIGURING)
            self.do_configure(state, params)
            self.abortable_transition(ss.ARMED)
        except AbortedError:
            assert self.abort_queue, "No abort queue"
            self.abort_queue.put(None)
            raise
        except Exception as e:
            self.go_to_error_state(e)
            raise
        else:
            return params

    def do_configure(self, state: str, params: ConfigureParams) -> None:
        if state == ss.FINISHED:
            # If we were finished then do a reset before configuring
            self.run_hooks(
                builtin.hooks.ResetHook(p, c)
                for p, c in self.create_part_contexts().items()
            )
        # Clear out any old part contexts now rather than letting gc do it
        for context in self.part_contexts.values():
            context.unsubscribe_all()
        # These are the part tasks that abort() and pause() will operate on
        self.part_contexts = self.create_part_contexts()
        # So add one for ourself too so we can be aborted
        assert self.process, "No attached process"
        self.part_contexts[self] = Context(self.process)
        # Store the params for use in seek()
        self.configure_params = params
        # Tell everything to get into the right state to Configure
        self.run_hooks(PreConfigureHook(p, c) for p, c in self.part_contexts.items())
        # This will calculate what we need from the generator, possibly a long
        # call
        params.generator.prepare()
        # Set the steps attributes that we will do across many run() calls
        self.total_steps.set_value(params.generator.size)
        self.completed_steps.set_value(0)
        self.configured_steps.set_value(0)
        # TODO: We can be cleverer about this and support a different number
        # of steps per run for each run by examining the generator structure
        self.steps_per_run = self.get_steps_per_run(
            params.generator, params.axesToMove, params.breakpoints
        )
        # Get any status from all parts
        part_info = self.run_hooks(
            ReportStatusHook(p, c) for p, c in self.part_contexts.items()
        )
        # Run the configure command on all parts, passing them info from
        # ReportStatus. Parts should return any reporting info for PostConfigure
        completed_steps = 0
        self.breakpoint_index = 0
        steps_to_do = self.steps_per_run[self.breakpoint_index]
        part_info = self.run_hooks(
            ConfigureHook(p, c, completed_steps, steps_to_do, part_info, **kw)
            for p, c, kw in self._part_params()
        )
        # Take configuration info and reflect it as attribute updates
        self.run_hooks(
            PostConfigureHook(p, c, part_info) for p, c in self.part_contexts.items()
        )
        # Update the completed and configured steps
        self.configured_steps.set_value(steps_to_do)
        self.completed_steps.meta.display.set_limitHigh(params.generator.size)
        # Reset the progress of all child parts
        self.progress_updates = {}
        self.resume_queue = Queue()

    @add_call_types
    def run(self) -> None:
        """Run a device where configure() has already be called

        Normally it will return in Ready state. If setup for multiple-runs with
        a single configure() then it will return in Armed state. If the user
        aborts then it will return in Aborted state. If something goes wrong it
        will return in Fault state. If the user disables then it will return in
        Disabled state.
        """

        # Run all PreRunHooks
        hook = PreRunHook
        self.do_pre_run(hook)

        if self.configured_steps.value < self.total_steps.value:
            next_state = ss.ARMED
        else:
            next_state = ss.FINISHED
        try:
            self.transition(ss.RUNNING)
            hook = RunHook
            going = True
            while going:
                try:
                    self.do_run(hook)
                    self.abortable_transition(next_state)
                except AbortedError:
                    assert self.abort_queue, "No abort queue"
                    self.abort_queue.put(None)
                    # Wait for a response on the resume_queue
                    assert self.resume_queue, "No resume queue"
                    should_resume = self.resume_queue.get()
                    if should_resume:
                        # we need to resume
                        self.log.debug("Resuming run")
                    else:
                        # we don't need to resume, just drop out
                        raise
                else:
                    going = False
        except AbortedError:
            raise
        except Exception as e:
            self.go_to_error_state(e)
            raise

    def do_pre_run(self, hook: Type[ControllerHook]) -> None:
        self.run_hooks(hook(p, c) for p, c in self.part_contexts.items())

    def do_run(self, hook: Type[ControllerHook]) -> None:
        self.run_hooks(hook(p, c) for p, c in self.part_contexts.items())
        self.abortable_transition(ss.POSTRUN)
        completed_steps = self.configured_steps.value
        if completed_steps < self.total_steps.value:
            if self.use_breakpoints:
                self.breakpoint_index += 1
            steps_to_do = self.steps_per_run[self.breakpoint_index]
            part_info = self.run_hooks(
                ReportStatusHook(p, c) for p, c in self.part_contexts.items()
            )
            self.completed_steps.set_value(completed_steps)
            self.run_hooks(
                PostRunArmedHook(
                    p, c, completed_steps, steps_to_do, part_info, **kwargs
                )
                for p, c, kwargs in self._part_params()
            )
            self.configured_steps.set_value(completed_steps + steps_to_do)
        else:
            self.completed_steps.set_value(completed_steps)
            self.run_hooks(
                PostRunReadyHook(p, c) for p, c in self.part_contexts.items()
            )

    def update_completed_steps(
        self, part: Part, completed_steps: RunProgressInfo
    ) -> None:
        with self._lock:
            # Update
            assert self.progress_updates is not None, "No progress updates"
            self.progress_updates[part] = completed_steps.steps
            min_completed_steps = min(self.progress_updates.values())
            if min_completed_steps > self.completed_steps.value:
                self.completed_steps.set_value(min_completed_steps)

    @add_call_types
    def abort(self) -> None:
        """Abort the current operation and block until aborted

        Normally it will return in Aborted state. If something goes wrong it
        will return in Fault state. If the user disables then it will return in
        Disabled state.
        """
        self.try_aborting_function(ss.ABORTING, ss.ABORTED, self.do_abort)
        # Tell _call_do_run not to resume
        if self.resume_queue:
            self.resume_queue.put(False)

    def do_abort(self) -> None:
        self.run_hooks(AbortHook(p, c) for p, c in self.create_part_contexts().items())

    def try_aborting_function(
        self, start_state: str, end_state: str, func: Callable[..., None], *args: Any
    ) -> None:
        try:
            # To make the running function fail we need to stop any running
            # contexts (if running a hook) or make transition() fail with
            # AbortedError. Both of these are accomplished here
            with self._lock:
                original_state = self.state.value
                self.abort_queue = Queue()
                self.transition(start_state)
                for context in self.part_contexts.values():
                    context.stop()
            if original_state not in (ss.READY, ss.ARMED, ss.PAUSED, ss.FINISHED):
                # Something was running, let it finish aborting
                try:
                    self.abort_queue.get(timeout=DEFAULT_TIMEOUT)
                except TimeoutError:
                    self.log.warning("Timeout waiting while {start_state}")
            with self._lock:
                # Now we've waited for a while we can remove the error state
                # for transition in case a hook triggered it rather than a
                # transition
                self_ctx = self.part_contexts.get(self, None)
                if self_ctx:
                    self_ctx.ignore_stops_before_now()
            func(*args)
            self.abortable_transition(end_state)
        except AbortedError:
            assert self.abort_queue, "No abort queue"
            self.abort_queue.put(None)
            raise
        except Exception as e:  # pylint:disable=broad-except
            self.go_to_error_state(e)
            raise

    # Allow camelCase as this will be serialized
    # noinspection PyPep8Naming
    @add_call_types
    def pause(self, lastGoodStep: ALastGoodStep = -1) -> None:
        """Pause a run() so that resume() can be called later, or seek within
        an Armed or Paused state.

        The original call to run() will not be interrupted by pause(), it will
        wait until the scan completes or is aborted.

        Normally it will return in Paused state. If the user aborts then it will
        return in Aborted state. If something goes wrong it will return in Fault
        state. If the user disables then it will return in Disabled state.
        """
        total_steps = self.total_steps.value

        # Always cap lastGoodStep to bounds of scan
        if lastGoodStep < 0:
            lastGoodStep = self.completed_steps.value
        elif lastGoodStep >= total_steps:
            lastGoodStep = total_steps - 1

        if self.state.value in [ss.ARMED, ss.FINISHED]:
            # We don't have a run process, free to go anywhere we want
            next_state = ss.ARMED
        else:
            # Need to pause within the bounds of the current run
            if lastGoodStep == self.configured_steps.value:
                lastGoodStep -= 1
            next_state = ss.PAUSED

        self.try_aborting_function(ss.SEEKING, next_state, self.do_pause, lastGoodStep)

    def do_pause(self, completed_steps: int) -> None:
        """Recalculates the number of configured steps
        Arguments:
        completed_steps -- Last good step performed
        """
        self.run_hooks(PauseHook(p, c) for p, c in self.create_part_contexts().items())

        if self.use_breakpoints:
            self.breakpoint_index -= 1
            in_run_steps = (
                completed_steps % self.breakpoint_steps[self.breakpoint_index]
            )
            steps_to_do = self.breakpoint_steps[self.breakpoint_index] - in_run_steps
        else:
            in_run_steps = completed_steps % self.steps_per_run[self.breakpoint_index]
            steps_to_do = self.steps_per_run[self.breakpoint_index] - in_run_steps

        part_info = self.run_hooks(
            ReportStatusHook(p, c) for p, c in self.part_contexts.items()
        )
        self.completed_steps.set_value(completed_steps)
        self.run_hooks(
            SeekHook(p, c, completed_steps, steps_to_do, part_info, **kwargs)
            for p, c, kwargs in self._part_params()
        )
        self.configured_steps.set_value(completed_steps + steps_to_do)

    @add_call_types
    def resume(self) -> None:
        """Resume a paused scan.

        Normally it will return in Running state. If something goes wrong it
        will return in Fault state.
        """
        self.transition(ss.RUNNING)
        assert self.resume_queue, "No resume queue"
        self.resume_queue.put(True)
        # self.run will now take over

    def do_disable(self) -> None:
        # Abort anything that is currently running, but don't wait
        for context in self.part_contexts.values():
            context.stop()
        if self.resume_queue:
            self.resume_queue.put(False)
        super().do_disable()

    def go_to_error_state(self, exception):
        if self.resume_queue:
            self.resume_queue.put(False)
        super().go_to_error_state(exception)
