from typing import Any

from malcolm.core import Context
from malcolm.modules import ADCore, builtin, scanning


@builtin.util.no_save(
    "collectMode",
    "pixelAdvanceMode",
    "presetMode",
    "ignoreGate",
    "pixelsPerRun",
    "autoPixelsPerBuffer",
    "pixelsPerBuffer",
    "binsInSpectrum",
    "inputLogicPolarity",
)
class XmapDriverPart(ADCore.parts.DetectorDriverPart):
    """Part for using xmap_driver_block in a scan"""

    def setup_detector(
        self,
        context: Context,
        completed_steps: scanning.hooks.ACompletedSteps,
        steps_to_do: scanning.hooks.AStepsToDo,
        steps_in_run: scanning.hooks.AStepsInRun,
        duration: float,
        part_info: scanning.hooks.APartInfo,
        **kwargs: Any,
    ) -> None:
        super().setup_detector(
            context,
            completed_steps,
            steps_to_do,
            steps_in_run,
            duration,
            part_info,
            collectMode="MCA mapping",
            pixelAdvanceMode="Gate",
            presetMode="No preset",
            ignoreGate="No",
            pixelsPerRun=steps_to_do,
            autoPixelsPerBuffer="Manual",
            pixelsPerBuffer=1,
            binsInSpectrum=2048,
            inputLogicPolarity="Normal",
            **kwargs,
        )
