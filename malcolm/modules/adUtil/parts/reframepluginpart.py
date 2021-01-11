from typing import Any

from annotypes import Anno, add_call_types

from malcolm.core import Context, PartRegistrar
from malcolm.modules import ADCore, builtin, scanning

with Anno("Sample frequency of ADC signal in Hz"):
    ASampleFreq = float

# Pull re-used annotypes into our namespace in case we are subclassed
APartName = ADCore.parts.APartName
AMri = ADCore.parts.AMri


# We will set these attributes on the child block, so don't save them
@builtin.util.no_save("postCount")
class ReframePluginPart(ADCore.parts.DetectorDriverPart):
    def __init__(
        self, name: APartName, mri: AMri, sample_freq: ASampleFreq = 10000.0
    ) -> None:
        super().__init__(name, mri)
        self.sample_freq = sample_freq

    def setup(self, registrar: PartRegistrar) -> None:
        super().setup(registrar)
        # Hooks
        registrar.hook(scanning.hooks.ValidateHook, self.on_validate)

    @add_call_types
    def on_validate(self, generator: scanning.hooks.AGenerator) -> None:
        exposure = generator.duration
        assert exposure > 0, (
            "Duration %s for generator must be >0 to signify fixed exposure" % exposure
        )
        nsamples = int(exposure * self.sample_freq) - 1
        assert nsamples > 0, "Duration %s for generator gives < 1 ADC sample" % exposure

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
        nsamples = int(duration * self.sample_freq) - 1
        super().setup_detector(
            context,
            completed_steps,
            steps_to_do,
            steps_in_run,
            duration,
            part_info,
            postCount=nsamples,
            **kwargs,
        )
