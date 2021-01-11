from typing import Any, Callable, Dict, Mapping, Sequence, TypeVar, Union

import numpy as np
from annotypes import NO_DEFAULT, Anno, Array
from scanpointgenerator import CompoundGenerator

from malcolm.compat import OrderedDict
from malcolm.core import VMeta
from malcolm.modules import builtin

from .infos import ConfigureParamsInfo, Info, ParameterTweakInfo

T = TypeVar("T")

with Anno("The Infos returned from other Parts"):
    APartInfo = Mapping[str, Array[Info]]
UPartInfo = Union[APartInfo, Mapping[str, Sequence[Info]]]
with Anno("Infos about current Part status to be passed to other parts"):
    AInfos = Union[Array[Info]]

with Anno("Generator instance providing specification for scan"):
    AGenerator = Union[CompoundGenerator]
with Anno("List of axes in inner dimension of generator that should be moved"):
    AAxesToMove = Union[Array[str]]
UAxesToMove = Union[AAxesToMove, Sequence[str]]
with Anno("List of points at which the run will return in Armed state"):
    ABreakpoints = Union[Array[np.int32]]
UBreakpoints = Union[ABreakpoints, Sequence[int]]
with Anno("Parameters that need to be changed to make them compatible"):
    AParameterTweakInfos = Union[Array[ParameterTweakInfo]]
UInfos = Union[AInfos, Sequence[Info], Info, None]
UParameterTweakInfos = Union[
    AParameterTweakInfos, Sequence[ParameterTweakInfo], ParameterTweakInfo, None
]
with Anno("Directory to write data to"):
    AFileDir = str
with Anno("Argument for fileTemplate, normally filename without extension"):
    AFormatName = str
with Anno(
    """Printf style template to generate filename relative to fileDir.
Arguments are:
  1) %s: the value of formatName"""
):
    AFileTemplate = str
with Anno("The demand exposure time of this scan, 0 for the maximum possible"):
    AExposure = float

# Pull re-used annotypes into our namespace in case we are subclassed
APart = builtin.hooks.APart
AContext = builtin.hooks.AContext
# also bring in superclass which a subclasses may refer to
ControllerHook = builtin.hooks.ControllerHook


def check_array_info(anno: Array, value: Any) -> T:
    assert anno.is_array and issubclass(anno.typ, Info), (
        "Expected Anno wrapping Array[something], got %s" % anno
    )
    ret = anno(value)
    bad = [x for x in ret if not isinstance(x, anno.typ)]
    assert not bad, "Passed objects %s that are not of type %s" % (bad, anno.typ)
    return ret


class ValidateHook(ControllerHook[UParameterTweakInfos]):
    """Called at validate() to check parameters are valid"""

    # Allow CamelCase for axesToMove as it must match ConfigureParams which
    # will become a configure argument, so must be camelCase to match EPICS
    # normative types conventions
    # noinspection PyPep8Naming
    def __init__(
        self,
        part: APart,
        context: AContext,
        part_info: UPartInfo,
        generator: AGenerator,
        axesToMove: AAxesToMove,
        breakpoints: ABreakpoints,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            part,
            context,
            part_info=part_info,
            generator=generator,
            axesToMove=axesToMove,
            breakpoints=breakpoints,
            **kwargs,
        )

    def validate_return(self, ret: UParameterTweakInfos) -> AParameterTweakInfos:
        """Check that all returned infos are ParameterTweakInfo that list
        the parameters that need to be changed to make them compatible with
        this part. ValidateHook will be re-run with the modified parameters."""
        return check_array_info(AParameterTweakInfos, ret)


class ReportStatusHook(ControllerHook[UInfos]):
    """Called before Validate, Configure, PostRunArmed and Seek hooks to report
    the current configuration of all parts"""

    def validate_return(self, ret: UInfos) -> AInfos:
        """Check that all parts return Info objects relevant to other parts"""
        return check_array_info(AInfos, ret)


with Anno("Number of steps already completed"):
    ACompletedSteps = int
with Anno("Number of steps we should configure for"):
    AStepsToDo = int
with Anno("Number of steps each run"):
    AStepsInRun = int


class PreConfigureHook(ControllerHook[None]):
    """Called before configure() to get the device into a suitable state to
    report status and run configure. Typically will load a saved design."""


class ConfigureHook(ControllerHook[UInfos]):
    """Called at configure() to configure child block for a run"""

    # Allow CamelCase for axesToMove as it must match ConfigureParams which
    # will become a configure argument, so must be camelCase to match EPICS
    # normative types conventions
    # noinspection PyPep8Naming
    def __init__(
        self,
        part: APart,
        context: AContext,
        completed_steps: ACompletedSteps,
        steps_to_do: AStepsToDo,
        part_info: APartInfo,
        generator: AGenerator,
        axesToMove: AAxesToMove,
        breakpoints: ABreakpoints,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            part,
            context,
            completed_steps=completed_steps,
            steps_to_do=steps_to_do,
            part_info=part_info,
            generator=generator,
            axesToMove=axesToMove,
            breakpoints=breakpoints,
            **kwargs,
        )

    @classmethod
    def create_info(cls, configure_func: Callable) -> ConfigureParamsInfo:
        """Create a `ConfigureParamsInfo` describing the extra parameters
        that should be passed at configure"""
        call_types: Dict[str, Anno] = getattr(configure_func, "call_types", {})
        metas = OrderedDict()
        required = []
        defaults = OrderedDict()
        for k, anno in call_types.items():
            if k not in cls.call_types:
                scls = VMeta.lookup_annotype_converter(anno)
                metas[k] = scls.from_annotype(anno, writeable=True)
                if anno.default is NO_DEFAULT:
                    required.append(k)
                elif anno.default is not None:
                    defaults[k] = anno.default
        return ConfigureParamsInfo(metas, required, defaults)

    def validate_return(self, ret: UInfos) -> AInfos:
        """Check that all parts return Info objects for storing as attributes"""
        return check_array_info(AInfos, ret)


class PostConfigureHook(ControllerHook[None]):
    """Called at the end of configure() to store configuration info calculated
    in the Configure hook"""

    def __init__(self, part: APart, context: AContext, part_info: APartInfo) -> None:
        super().__init__(part, context, part_info=part_info)


class PreRunHook(ControllerHook[None]):
    """Called at the start of run()"""


class RunHook(ControllerHook[None]):
    """Called at run() to start the configured steps running"""


class PostRunArmedHook(ControllerHook[None]):
    """Called at the end of run() when there are more steps to be run"""

    # Allow CamelCase for axesToMove as it must match ConfigureParams which
    # will become a configure argument, so must be camelCase to match EPICS
    # normative types conventions
    # noinspection PyPep8Naming
    def __init__(
        self,
        part: APart,
        context: AContext,
        completed_steps: ACompletedSteps,
        steps_to_do: AStepsToDo,
        part_info: UPartInfo,
        generator: AGenerator,
        axesToMove: AAxesToMove,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            part,
            context,
            completed_steps=completed_steps,
            steps_to_do=steps_to_do,
            part_info=part_info,
            generator=generator,
            axesToMove=axesToMove,
            **kwargs,
        )


class PostRunReadyHook(ControllerHook[None]):
    """Called at the end of run() when there are no more steps to be run"""


class PauseHook(ControllerHook[None]):
    """Called at pause() to pause the current scan before Seek is called"""


class SeekHook(ControllerHook[None]):
    """Called at seek() or at the end of pause() to reconfigure for a different
    number of completed_steps"""

    # Allow CamelCase for axesToMove as it must match ConfigureParams which
    # will become a configure argument, so must be camelCase to match EPICS
    # normative types conventions
    # noinspection PyPep8Naming
    def __init__(
        self,
        part: APart,
        context: AContext,
        completed_steps: ACompletedSteps,
        steps_to_do: AStepsToDo,
        part_info: APartInfo,
        generator: AGenerator,
        axesToMove: AAxesToMove,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            part,
            context,
            completed_steps=completed_steps,
            steps_to_do=steps_to_do,
            part_info=part_info,
            generator=generator,
            axesToMove=axesToMove,
            **kwargs,
        )


class AbortHook(ControllerHook[None]):
    """Called at abort() to stop the current scan"""
