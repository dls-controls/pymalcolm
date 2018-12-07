from annotypes import add_call_types, Any

from malcolm.modules import ADCore, scanning


class AndorDriverPart(ADCore.parts.DetectorDriverPart):
    @add_call_types
    def configure(self,
                  context,  # type: scanning.hooks.AContext
                  completed_steps,  # type: scanning.hooks.ACompletedSteps
                  steps_to_do,  # type: scanning.hooks.AStepsToDo
                  part_info,  # type: scanning.hooks.APartInfo
                  generator,  # type: scanning.hooks.AGenerator
                  **kwargs  # type: **Any
                  ):
        # type: (...) -> None
        exposure_info = ADCore.infos.ExposureDeadtimeInfo.filter_single_value(
            part_info)
        self.actions.setup_detector(
            context, completed_steps, steps_to_do,
            exposure=exposure_info.calculate_exposure(generator.duration),
            imageMode="Fixed", **kwargs)
        # Need to reset acquirePeriod as it's sometimes wrong
        child = context.block_view(self.mri)
        child.acquirePeriod.put_value(generator.duration)
        # Start now if we are hardware triggered
        # self.is_hardware_triggered = child.triggerMode == "Hardware"
        if self.is_hardware_triggered:
            self.actions.arm_detector(context)
