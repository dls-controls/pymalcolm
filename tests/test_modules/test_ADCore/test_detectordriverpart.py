from xml.etree import ElementTree

from mock import MagicMock, call
from scanpointgenerator import CompoundGenerator, LineGenerator

from malcolm.core import Context, IncompatibleError, Process
from malcolm.modules.ADCore.includes import adbase_parts
from malcolm.modules.ADCore.infos import FilePathTranslatorInfo
from malcolm.modules.ADCore.parts import DetectorDriverPart
from malcolm.modules.ADCore.util import (
    AttributeDatasetType,
    DataType,
    ExtraAttributesTable,
    SourceType,
)
from malcolm.modules.builtin.controllers import StatefulController
from malcolm.modules.scanning.infos import ExposureDeadtimeInfo
from malcolm.testutil import ChildTestCase

expected_xml = (
    '<?xml version="1.0" ?>\n'
    "<Attributes>\n"
    '<Attribute dbrtype="DBR_NATIVE" description="a test pv" '
    'name="test1" source="PV1" type="EPICS_PV" />\n'
    '<Attribute dbrtype="DBR_DOUBLE" description="another test PV" '
    'name="test2" source="PV2" type="EPICS_PV" />\n'
    '<Attribute datatype="DOUBLE" description="a param, for testing" '
    'name="test3" source="PARAM1" type="PARAM" />\n'
    "</Attributes>"
)


class TestDetectorDriverPart(ChildTestCase):
    def setUp(self):
        self.process = Process("Process")
        self.context = Context(self.process)

        def child_block():
            controllers, parts = adbase_parts(prefix="prefix")
            controller = StatefulController("mri")
            for part in parts:
                controller.add_part(part)
            return controllers + [controller]

        self.child = self.create_child_block(child_block, self.process)
        self.mock_when_value_matches(self.child)
        self.o = DetectorDriverPart(
            name="m", mri="mri", soft_trigger_modes=["Internal"]
        )
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        self.process.start()

    def tearDown(self):
        self.process.stop(timeout=2)

    def test_report(self):
        info = self.o.on_report_status()
        assert len(info) == 1
        assert info[0].rank == 2

    def test_configure(self):
        xs = LineGenerator("x", "mm", 0.0, 0.5, 3, alternate=True)
        ys = LineGenerator("y", "mm", 0.0, 0.1, 2)
        generator = CompoundGenerator([ys, xs], [], [], 0.1)
        generator.prepare()
        completed_steps = 0
        steps_to_do = 6
        info = ExposureDeadtimeInfo(0.01, 1000, 0.0)
        part_info = dict(anyname=[info])
        self.set_attributes(self.child, triggerMode="Internal")
        self.o.on_configure(
            self.context,
            completed_steps,
            steps_to_do,
            part_info,
            generator,
            fileDir="/tmp",
            exposure=info.calculate_exposure(generator.duration),
        )
        assert self.child.handled_requests.mock_calls == [
            call.put("arrayCallbacks", True),
            call.put("arrayCounter", 0),
            call.put("exposure", 0.1 - 0.01 - 0.0001),
            call.put("imageMode", "Multiple"),
            call.put("numImages", 6),
            call.put("acquirePeriod", 0.1 - 0.0001),
        ]
        assert not self.o.is_hardware_triggered

    def test_configure_with_extra_attributes(self):
        xs = LineGenerator("x", "mm", 0.0, 0.5, 3, alternate=True)
        ys = LineGenerator("y", "mm", 0.0, 0.1, 2)
        generator = CompoundGenerator([ys, xs], [], [], 0.1)
        generator.prepare()
        completed_steps = 0
        steps_to_do = 6
        expected_xml_filename = "/tmp/mri-attributes.xml"
        self.set_attributes(self.child, triggerMode="Internal")
        extra_attributes = ExtraAttributesTable(
            name=["test1", "test2", "test3"],
            sourceId=["PV1", "PV2", "PARAM1"],
            sourceType=[SourceType.PV, SourceType.PV, SourceType.PARAM],
            description=["a test pv", "another test PV", "a param, for testing"],
            dataType=[DataType.DBRNATIVE, DataType.DOUBLE, DataType.DOUBLE],
            datasetType=[
                AttributeDatasetType.MONITOR,
                AttributeDatasetType.DETECTOR,
                AttributeDatasetType.POSITION,
            ],
        )
        self.o.extra_attributes.set_value(extra_attributes)
        self.o.on_configure(
            self.context, completed_steps, steps_to_do, {}, generator, fileDir="/tmp"
        )
        assert self.child.handled_requests.mock_calls == [
            call.put("arrayCallbacks", True),
            call.put("arrayCounter", 0),
            call.put("imageMode", "Multiple"),
            call.put("numImages", 6),
            call.put("attributesFile", expected_xml_filename),
        ]
        assert not self.o.is_hardware_triggered
        with open(expected_xml_filename) as f:
            actual_xml = f.read().replace(">", ">\n")

        actual_tree = ElementTree.XML(actual_xml)
        expected_tree = ElementTree.XML(expected_xml)
        assert ElementTree.dump(actual_tree) == ElementTree.dump(expected_tree)

    def test_version_check(self):
        block = self.context.block_view("mri")
        self.o.required_version = "2.2"
        self.set_attributes(self.child, driverVersion="1.9")
        self.assertRaises(IncompatibleError, self.o.check_driver_version, block)
        self.set_attributes(self.child, driverVersion="2.1")
        self.assertRaises(IncompatibleError, self.o.check_driver_version, block)
        self.set_attributes(self.child, driverVersion="3.0")
        self.assertRaises(IncompatibleError, self.o.check_driver_version, block)
        self.set_attributes(self.child, driverVersion="2.2")
        self.o.check_driver_version(block)
        self.set_attributes(self.child, driverVersion="2.2.3")
        self.o.check_driver_version(block)

    def test_run(self):
        self.o.registrar = MagicMock()
        # This would have been done by configure
        self.o.is_hardware_triggered = False
        self.o.on_run(self.context)
        assert self.child.handled_requests.mock_calls == [
            call.post("start"),
            call.when_value_matches("acquiring", True, None),
            call.when_value_matches("arrayCounterReadback", 0, None),
        ]
        assert self.o.registrar.report.call_count == 2
        assert self.o.registrar.report.call_args[0][0].steps == 0

    def test_hardware_triggered_run(self):
        self.o.registrar = MagicMock()
        # This would have been done by configure
        self.o.is_hardware_triggered = True
        self.o.on_run(self.context)
        # Should not call start when hardware triggered
        assert self.child.handled_requests.mock_calls == [
            call.when_value_matches("arrayCounterReadback", 0, None),
        ]
        assert self.o.registrar.report.call_count == 2
        assert self.o.registrar.report.call_args[0][0].steps == 0

    def test_post_run_armed(self):
        # This would have been done by configure
        self.o.is_hardware_triggered = False
        self.o.done_when_reaches = 100
        self.o.on_post_run_armed(self.context, steps_to_do=100)
        assert self.o.done_when_reaches == 100

    def test_hardware_triggered_post_run_armed(self):
        # This would have been done by configure
        self.o.is_hardware_triggered = True
        self.o.done_when_reaches = 100
        self.o.on_post_run_armed(self.context, steps_to_do=100)
        assert self.o.done_when_reaches == 200

    def test_abort(self):
        self.o.on_abort(self.context)
        assert self.child.handled_requests.mock_calls == [
            call.post("stop"),
            call.when_value_matches("acquiring", False, None),
        ]


class TestDetectorDriverPartNestedConfigure(TestDetectorDriverPart):
    def setUp(self):
        super().setUp()
        # In this case we only move x and expect energy to be moved in between runs
        outer = LineGenerator("energy", "keV", 10.0, 11.0, 5)
        self.steps_to_do = 10
        inner = LineGenerator("x", "mm", 0.0, 0.5, self.steps_to_do)
        self.generator = CompoundGenerator([outer, inner], [], [], 0.1)
        self.generator.prepare()
        self.completed_steps = 0
        self.info = ExposureDeadtimeInfo(0.01, 1000, 0.0)
        self.part_info = dict(anyname=[self.info])

    def configure(self):
        self.o.on_configure(
            self.context,
            self.completed_steps,
            self.steps_to_do,
            self.part_info,
            self.generator,
            fileDir="/tmp",
            exposure=self.info.calculate_exposure(self.generator.duration),
        )

    def test_nested_configure(self):
        self.set_attributes(self.child, triggerMode="Internal")
        self.configure()
        # When not hardware triggered we set numImages for the inner scan only
        assert self.child.handled_requests.mock_calls == [
            call.put("arrayCallbacks", True),
            call.put("arrayCounter", 0),
            call.put("exposure", 0.1 - 0.01 - 0.0001),
            call.put("imageMode", "Multiple"),
            call.put("numImages", 10),
            call.put("acquirePeriod", 0.1 - 0.0001),
        ]

    def test_nested_hardware_triggered_configure(self):
        self.set_attributes(self.child, triggerMode="External")
        self.configure()
        # When hardware triggered we set numImages to the total frames and call start
        assert self.child.handled_requests.mock_calls == [
            call.put("arrayCallbacks", True),
            call.put("arrayCounter", 0),
            call.put("exposure", 0.1 - 0.01 - 0.0001),
            call.put("imageMode", "Multiple"),
            call.put("numImages", 50),
            call.put("acquirePeriod", 0.1 - 0.0001),
            call.post("start"),
            call.when_value_matches("acquiring", True, None),
        ]


class TestDetectorDriverPartWindows(ChildTestCase):
    def setUp(self):
        self.process = Process("Process")
        self.context = Context(self.process)

        def child_block():
            controllers, parts = adbase_parts(prefix="prefix")
            controller = StatefulController("WINDOWS:DETECTOR")
            for part in parts:
                controller.add_part(part)
            return controllers + [controller]

        self.child = self.create_child_block(child_block, self.process)
        self.mock_when_value_matches(self.child)
        self.o = DetectorDriverPart(
            name="m",
            mri="WINDOWS:DETECTOR",
            soft_trigger_modes=["Internal"],
            runs_on_windows=True,
        )
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        self.process.start()

    def tearDown(self):
        self.process.stop(timeout=2)

    def test_configure_on_windows(self):
        """Test the network mount drive on Windows"""
        xs = LineGenerator("x", "mm", 0.0, 0.5, 3, alternate=True)
        ys = LineGenerator("y", "mm", 0.0, 0.1, 2)
        generator = CompoundGenerator([ys, xs], [], [], 0.1)
        generator.prepare()
        completed_steps = 0
        steps_to_do = 6
        expected_xml_filename = "\\\\dc\\tmp\\WINDOWS_DETECTOR-attributes.xml"
        self.set_attributes(self.child, triggerMode="Internal")
        extra_attributes = ExtraAttributesTable(
            name=["test1", "test2", "test3"],
            sourceId=["PV1", "PV2", "PARAM1"],
            sourceType=[SourceType.PV, SourceType.PV, SourceType.PARAM],
            description=["a test pv", "another test PV", "a param, for testing"],
            dataType=[DataType.DBRNATIVE, DataType.DOUBLE, DataType.DOUBLE],
            datasetType=[
                AttributeDatasetType.MONITOR,
                AttributeDatasetType.DETECTOR,
                AttributeDatasetType.POSITION,
            ],
        )
        self.o.extra_attributes.set_value(extra_attributes)
        win_info = FilePathTranslatorInfo("", "/tmp", "//dc")
        part_info = dict(anyname=[win_info])
        self.o.on_configure(
            self.context,
            completed_steps,
            steps_to_do,
            part_info,
            generator,
            fileDir="/tmp",
        )
        assert self.child.handled_requests.mock_calls == [
            call.put("arrayCallbacks", True),
            call.put("arrayCounter", 0),
            call.put("imageMode", "Multiple"),
            call.put("numImages", 6),
            call.put("attributesFile", expected_xml_filename),
        ]
        assert not self.o.is_hardware_triggered
