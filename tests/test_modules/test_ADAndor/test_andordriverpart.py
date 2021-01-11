import pytest
from mock import Mock, call, patch
from scanpointgenerator import CompoundGenerator, LineGenerator

from malcolm.core import Context, Process
from malcolm.modules.ADAndor.blocks import andor_driver_block
from malcolm.modules.ADAndor.parts import AndorDriverPart
from malcolm.testutil import ChildTestCase


class TestAndorDetectorDriverPart(ChildTestCase):
    def setUp(self):
        self.process = Process("Process")
        self.context = Context(self.process)
        self.child = self.create_child_block(
            andor_driver_block, self.process, mri="mri", prefix="prefix"
        )
        self.mock_when_value_matches(self.child)
        # readoutTime used to be 0.002, not any more...
        self.andor_driver_part = AndorDriverPart(name="m", mri="mri")
        self.context.set_notify_dispatch_request(
            self.andor_driver_part.notify_dispatch_request
        )
        self.process.start()

    def tearDown(self):
        self.process.stop(timeout=1)

    def do_configure(self):
        xs = LineGenerator("x", "mm", 0.0, 0.5, 3000, alternate=True)
        ys = LineGenerator("y", "mm", 0.0, 0.1, 2000)
        generator = CompoundGenerator([ys, xs], [], [], 0.1)
        generator.prepare()
        completed_steps = 0
        steps_to_do = 2000 * 3000
        file_dir = "/tmp"
        self.andor_driver_part.on_configure(
            self.context,
            completed_steps,
            steps_to_do,
            {},
            generator=generator,
            fileDir=file_dir,
        )

    def test_configure(self):
        # We wait to be armed, so set this here
        self.set_attributes(self.child, acquiring=True)
        # This is what the detector does when exposure and acquirePeriod are
        # both set to 0.1
        self.set_attributes(self.child, exposure=0.1, acquirePeriod=0.105)
        self.do_configure()
        # duration - readout - fudge_factor - crystal offset
        expected_exposure = pytest.approx(0.1 - 0.005 - 0.0014 - 5e-6)
        assert self.child.handled_requests.mock_calls == [
            # Checking for readout time
            call.put("exposure", 0.1),
            call.put("acquirePeriod", 0.1),
            # Setup of detector
            call.put("arrayCallbacks", True),
            call.put("arrayCounter", 0),
            call.put("exposure", expected_exposure),
            call.put("imageMode", "Multiple"),
            call.put("numImages", 6000000),
            call.put("acquirePeriod", 0.1 - 5e-6),
            call.post("start"),
            call.when_value_matches("acquiring", True, None),
        ]
        assert self.andor_driver_part.exposure.value == expected_exposure

    def test_configure_frame_transfer(self):
        accumulate_period = 0.08
        # We wait to be armed, so set this here
        self.set_attributes(self.child, acquiring=True)
        # Set what we need to simulate frame transfer mode
        self.set_attributes(
            self.child,
            andorFrameTransferMode=True,
            andorAccumulatePeriod=accumulate_period,
        )
        self.do_configure()
        assert self.child.handled_requests.mock_calls == [
            call.put("exposure", 0.0),
            call.put("acquirePeriod", 0.0),
            call.put("arrayCallbacks", True),
            call.put("arrayCounter", 0),
            call.put("exposure", 0.0),
            call.put("imageMode", "Multiple"),
            call.put("numImages", 6000000),
            call.put("acquirePeriod", accumulate_period),
            call.post("start"),
            call.when_value_matches("acquiring", True, None),
        ]

    @patch("malcolm.modules.ADCore.parts.DetectorDriverPart.setup_detector")
    def test_setup_detector_overwrites_exposure_in_kwargs_no_frame_transfer_mode(
        self, super_setup_detector_mock
    ):
        # Mock our arguments
        completed_steps = Mock(name="completed_steps_mock")
        steps_to_do = Mock(name="steps_to_do_mock")
        duration = 0.1
        actual_exposure = 0.09
        actual_period = 0.098
        part_info = Mock(name="part_info")

        # Mock the adjusted_exposure_time_and_acquire_period_method
        adjusted_acquisition_mock = Mock(name="adjusted_acquisition_mock")
        adjusted_acquisition_mock.return_value = (actual_exposure, actual_period)
        self.andor_driver_part.get_adjusted_exposure_time_and_acquire_period = (
            adjusted_acquisition_mock
        )

        self.andor_driver_part.setup_detector(
            self.context,
            completed_steps,
            steps_to_do,
            steps_to_do,
            duration,
            part_info,
            exposure=0.05,
        )

        # Check method calls
        assert self.child.handled_requests.mock_calls == [
            call.put("exposure", duration),
            call.put("acquirePeriod", duration),
            call.put("acquirePeriod", actual_period),
        ]

        super_setup_detector_mock.assert_called_once_with(
            self.context,
            completed_steps,
            steps_to_do,
            steps_to_do,
            duration,
            part_info,
            exposure=actual_exposure,
        )

        # Check exposure time
        self.assertEqual(actual_exposure, self.andor_driver_part.exposure.value)

    @patch("malcolm.modules.ADCore.parts.DetectorDriverPart.setup_detector")
    def test_setup_detector_adds_exposure_in_kwargs_no_frame_transfer_mode(
        self, super_setup_detector_mock
    ):
        # Mock our arguments
        completed_steps = Mock(name="completed_steps_mock")
        steps_to_do = Mock(name="steps_to_do_mock")
        duration = 1.0
        actual_exposure = 0.99
        actual_period = 0.95
        part_info = Mock(name="part_info")

        # Mock the adjusted_exposure_time_and_acquire_period_method
        adjusted_acquisition_mock = Mock(name="adjusted_acquisition_mock")
        adjusted_acquisition_mock.return_value = (actual_exposure, actual_period)
        self.andor_driver_part.get_adjusted_exposure_time_and_acquire_period = (
            adjusted_acquisition_mock
        )

        self.andor_driver_part.setup_detector(
            self.context, completed_steps, steps_to_do, steps_to_do, duration, part_info
        )

        # Check method calls
        assert self.child.handled_requests.mock_calls == [
            call.put("exposure", duration),
            call.put("acquirePeriod", duration),
            call.put("acquirePeriod", actual_period),
        ]

        super_setup_detector_mock.assert_called_once_with(
            self.context,
            completed_steps,
            steps_to_do,
            steps_to_do,
            duration,
            part_info,
            exposure=actual_exposure,
        )

        # Check exposure time
        self.assertEqual(actual_exposure, self.andor_driver_part.exposure.value)

    @patch("malcolm.modules.ADCore.parts.DetectorDriverPart.setup_detector")
    def test_setup_detector_overwrites_exposure_in_kwargs_frame_transfer_mode(
        self, super_setup_detector_mock
    ):
        # Mock our arguments
        completed_steps = Mock(name="completed_steps_mock")
        steps_to_do = Mock(name="steps_to_do_mock")
        duration = 1.0
        actual_exposure = 0.0
        accumulate_period = 0.01
        part_info = Mock(name="part_info")

        # Turn on frame transfer mode and set accumulate period
        self.set_attributes(
            self.child,
            andorFrameTransferMode=True,
            andorAccumulatePeriod=accumulate_period,
        )

        self.andor_driver_part.setup_detector(
            self.context,
            completed_steps,
            steps_to_do,
            steps_to_do,
            duration,
            part_info,
            exposure=0.25,
        )

        # Check method calls
        assert self.child.handled_requests.mock_calls == [
            call.put("exposure", actual_exposure),
            call.put("acquirePeriod", actual_exposure),
            call.put("acquirePeriod", accumulate_period),
        ]

        super_setup_detector_mock.assert_called_once_with(
            self.context,
            completed_steps,
            steps_to_do,
            steps_to_do,
            duration,
            part_info,
            exposure=actual_exposure,
        )

        # Check exposure time
        self.assertEqual(actual_exposure, self.andor_driver_part.exposure.value)

    @patch("malcolm.modules.ADCore.parts.DetectorDriverPart.setup_detector")
    def test_setup_detector_adds_exposure_in_kwargs_frame_transfer_mode(
        self, super_setup_detector_mock
    ):
        # Mock our arguments
        completed_steps = Mock(name="completed_steps_mock")
        steps_to_do = Mock(name="steps_to_do_mock")
        duration = 1.0
        actual_exposure = 0.0
        accumulate_period = 0.01
        part_info = Mock(name="part_info")

        # Turn on frame transfer mode and set accumulate period
        self.set_attributes(
            self.child,
            andorFrameTransferMode=True,
            andorAccumulatePeriod=accumulate_period,
        )

        self.andor_driver_part.setup_detector(
            self.context, completed_steps, steps_to_do, steps_to_do, duration, part_info
        )

        # Check method calls
        assert self.child.handled_requests.mock_calls == [
            call.put("exposure", actual_exposure),
            call.put("acquirePeriod", actual_exposure),
            call.put("acquirePeriod", accumulate_period),
        ]

        super_setup_detector_mock.assert_called_once_with(
            self.context,
            completed_steps,
            steps_to_do,
            steps_to_do,
            duration,
            part_info,
            exposure=actual_exposure,
        )

        # Check exposure time
        self.assertEqual(actual_exposure, self.andor_driver_part.exposure.value)

    @patch("malcolm.modules.scanning.infos.ExposureDeadtimeInfo")
    def test_get_adjusted_exposure_time_and_acquire_period(
        self, exposure_deadtime_info_mock
    ):
        duration = 1.0
        readout_time = 0.1
        exposure_time = 0.9

        # Return a Mock when ExposureDeadtimeInfo constructor is called
        exposure_deadtime_info_instance_mock = Mock(
            name="exposure_deadtime_info_mock_instance"
        )
        exposure_deadtime_info_mock.return_value = exposure_deadtime_info_instance_mock

        # Mock the calculate exposure method of ExposureDeadtimeInfo
        total_readout_time = (
            readout_time
            + self.andor_driver_part.get_additional_readout_factor(duration)
        )
        exposure_deadtime_info_instance_mock.calculate_exposure.return_value = (
            exposure_time - total_readout_time
        )

        expected_exposure_time = exposure_time - total_readout_time
        expected_acquire_period = expected_exposure_time + total_readout_time

        (
            actual_exposure_time,
            actual_acquire_period,
        ) = self.andor_driver_part.get_adjusted_exposure_time_and_acquire_period(
            duration, readout_time, exposure_time
        )

        # Check calls
        exposure_deadtime_info_mock.assert_called_once_with(
            total_readout_time, frequency_accuracy=50, min_exposure=0.0
        )
        exposure_deadtime_info_instance_mock.calculate_exposure.assert_called_once_with(
            duration, exposure_time
        )

        # Check values
        self.assertEqual(expected_exposure_time, actual_exposure_time)
        self.assertEqual(expected_acquire_period, actual_acquire_period)

    def test_get_additional_readout_factor(self):
        duration = 0.5
        expected_readout_factor = duration * 0.004 + 0.001

        actual_readout_factor = self.andor_driver_part.get_additional_readout_factor(
            duration
        )

        self.assertEqual(expected_readout_factor, actual_readout_factor)
