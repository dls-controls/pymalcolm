from typing import Union

import numpy as np
from annotypes import Anno, Array, add_call_types

from malcolm.core import (
    DEFAULT_TIMEOUT,
    Display,
    IncompatibleError,
    NumberMeta,
    PartRegistrar,
    Widget,
)
from malcolm.modules import builtin

from ..util import CS_AXIS_NAMES

# recommended trajectory program number and lowest allowed program number
TRAJECTORY_PROGRAM_NUM = 3
FALLBACK_TRAJ_PROGRAM_NUM = 2

# The maximum number of points in a single trajectory scan
MAX_NUM_POINTS = 4000000

with Anno("The Asyn Port name of the Co-ordinate system port we want to scan"):
    ACSPort = str
with Anno("The relative time points to scan in microseconds"):
    ATimeArray = Union[Array[np.int32]]
with Anno("The velocity mode of each point"):
    AVelocityMode = Union[Array[np.int32]]
with Anno("Which user program to run for each point"):
    AUserPrograms = Union[Array[np.int32]]
with Anno("The position the axis should be at for each point in the scan"):
    ADemandTrajectory = Union[Array[np.float64]]
with Anno("The Velocity the axis should be at for each point in the scan"):
    ADemandVelocity = Union[Array[np.float64]]

# Pull re-used annotypes into our namespace in case we are subclassed
APartName = builtin.parts.APartName
AMri = builtin.parts.AMri


def _zeros_or_right_length(array, num_points):
    if array is None:
        array = np.zeros(num_points, np.int32)
    else:
        assert (
            len(array) == num_points
        ), f"Array {array} should be {num_points} points long"
    return array


# We will set these attributes on the child block, so don't save them
@builtin.util.no_save(
    "numPoints",
    "enableCallbacks",
    "computeStatistics",
    "timeArray",
    "cs",
    "velocityMode",
    "userPrograms",
    "pointsToBuild",
)
@builtin.util.no_save(f"use{x}" for x in CS_AXIS_NAMES)
@builtin.util.no_save(f"positions{x}" for x in CS_AXIS_NAMES)
class PmacTrajectoryPart(builtin.parts.ChildPart):
    def __init__(
        self,
        name: APartName,
        mri: AMri,
    ) -> None:
        super().__init__(name, mri, initial_visibility=True)
        # The total number of points we have written
        self.total_points = 0
        self.points_scanned = NumberMeta(
            "int32", "The number of points scanned", tags=[Widget.METER.tag()]
        ).create_attribute_model(0)

    def setup(self, registrar: PartRegistrar) -> None:
        super().setup(registrar)
        # Add methods
        registrar.add_method_model(
            self.write_profile, "writeProfile", needs_context=True
        )
        registrar.add_method_model(
            self.execute_profile, "executeProfile", needs_context=True
        )
        registrar.add_method_model(
            self.abort_profile, "abortProfile", needs_context=True
        )
        # Add Attributes
        registrar.add_attribute_model("pointsScanned", self.points_scanned)

    # Serialized, so use camelCase
    # noinspection PyPep8Naming
    @add_call_types
    def write_profile(
        self,
        context: builtin.hooks.AContext,
        timeArray: ATimeArray,
        csPort: ACSPort = None,
        velocityMode: AVelocityMode = None,
        userPrograms: AUserPrograms = None,
        a: ADemandTrajectory = None,
        a_vel: ADemandVelocity = None,
        b: ADemandTrajectory = None,
        b_vel: ADemandVelocity = None,
        c: ADemandTrajectory = None,
        c_vel: ADemandVelocity = None,
        u: ADemandTrajectory = None,
        u_vel: ADemandVelocity = None,
        v: ADemandTrajectory = None,
        v_vel: ADemandVelocity = None,
        w: ADemandTrajectory = None,
        w_vel: ADemandVelocity = None,
        x: ADemandTrajectory = None,
        x_vel: ADemandVelocity = None,
        y: ADemandTrajectory = None,
        y_vel: ADemandVelocity = None,
        z: ADemandTrajectory = None,
        z_vel: ADemandVelocity = None,
    ) -> None:
        child = context.block_view(self.mri)

        # make sure a matching trajectory program is installed on the pmac
        if child.trajectoryProgVersion.value < TRAJECTORY_PROGRAM_NUM:
            if child.trajectoryProgVersion.value >= FALLBACK_TRAJ_PROGRAM_NUM:
                self.log.warning(
                    f"pmac trajectory program is version {FALLBACK_TRAJ_PROGRAM_NUM}"
                    f" version {TRAJECTORY_PROGRAM_NUM} is recommended"
                )
            else:
                raise (
                    IncompatibleError(
                        f"pmac trajectory program {child.trajectoryProgVersion.value} "
                        f"detected. Malcolm requires {TRAJECTORY_PROGRAM_NUM}"
                    )
                )

        # The axes taking part in the scan
        use_axes = []
        for axis in CS_AXIS_NAMES:
            if locals()[axis.lower()] is not None:
                use_axes.append(axis)
        if csPort is not None:
            # This is a build
            action = child.buildProfile
            self.total_points = 0
            child.numPoints.put_value(MAX_NUM_POINTS)
            try:
                child.cs.put_value(csPort)
            except ValueError as e:
                raise ValueError(
                    f"Cannot set CS to {csPort}, did you use a compound_motor_block "
                    f"for a raw motor?\n{e}"
                )
            # Tell the trajectory scans which of the arrays to use
            arrays = {f"use{axis}": axis in use_axes for axis in CS_AXIS_NAMES}
            child.put_attribute_values(arrays)
        else:
            # This is an append
            action = child.appendProfile

        # Fill in the arrays
        num_points = len(timeArray)
        attribute_values = dict(
            timeArray=timeArray,
            pointsToBuild=num_points,
            velocityMode=_zeros_or_right_length(velocityMode, num_points),
            userPrograms=_zeros_or_right_length(userPrograms, num_points),
        )
        for axis in use_axes:
            demand = locals()[axis.lower()]
            demand_vel = locals()[axis.lower() + "_vel"]
            attribute_values[f"positions{axis}"] = demand
            attribute_values[f"velocities{axis}"] = demand_vel
        child.put_attribute_values(attribute_values)
        # Write the profile
        action()
        # Record how many points we have now written in total
        self.total_points += num_points

    def set_scan_length(self, value):
        self.points_scanned.meta.set_display(Display(limitHigh=value))

    @add_call_types
    def execute_profile(self, context: builtin.hooks.AContext) -> None:
        child = context.block_view(self.mri)
        fs1 = context.subscribe(
            [self.mri, "pointsScanned", "value"], self.points_scanned.set_value
        )
        fs2 = context.subscribe(
            [self.mri, "pointsBuilt", "value"], self.set_scan_length
        )
        try:
            child.executeProfile()
            # Now wait for up to 2*min_delta time to make sure any
            # update_completed_steps come in
            child.when_value_matches(
                "pointsScanned", self.total_points, timeout=DEFAULT_TIMEOUT
            )
        finally:
            context.unsubscribe(fs1)
            context.unsubscribe(fs2)

    @add_call_types
    def abort_profile(self, context: builtin.hooks.AContext) -> None:
        child = context.block_view(self.mri)
        child.abortProfile()
