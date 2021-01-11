from xml.etree import ElementTree

from mock import MagicMock, call

from malcolm.core import Context, Process
from malcolm.modules.ADCore.infos import FilePathTranslatorInfo
from malcolm.modules.ADCore.util import (
    AttributeDatasetType,
    DataType,
    ExtraAttributesTable,
    SourceType,
)
from malcolm.modules.xmap.blocks import xmap_driver_block
from malcolm.modules.xmap.parts import XmapDriverPart
from malcolm.testutil import ChildTestCase

expected_xml = (
    '<?xml version="1.0" ?>\n'
    "<Attributes>\n"
    '<Attribute dbrtype="DBR_LONG" description="a test pv" name="test1" source="PV1" '
    'type="EPICS_PV" />\n'
    '<Attribute dbrtype="DBR_STRING" description="another test PV" name="test2" '
    'source="PV2" type="EPICS_PV" />\n'
    '<Attribute datatype="STRING" description="a param, for testing" name="test3" '
    'source="PARAM1" type="PARAM" />\n'
    "</Attributes>"
)


class TestXmap3DetectorDriverPart(ChildTestCase):
    def setUp(self):
        self.process = Process("Process")
        self.context = Context(self.process)
        self.child = self.create_child_block(
            xmap_driver_block, self.process, mri="mri", prefix="prefix"
        )
        self.mock_when_value_matches(self.child)
        self.o = XmapDriverPart(name="m", mri="mri", runs_on_windows=True)
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        self.process.start()

    def tearDown(self):
        self.process.stop(timeout=1)

    def test_configure(self):
        completed_steps = 0
        steps_to_do = 456
        part_info = {"sth": [FilePathTranslatorInfo("Z", "/tmp", "")]}
        self.o.post_configure = MagicMock()
        # We wait to be armed, so set this here
        self.set_attributes(self.child, acquiring=True)

        extra_attributes = ExtraAttributesTable(
            name=["test1", "test2", "test3"],
            sourceId=["PV1", "PV2", "PARAM1"],
            sourceType=[SourceType.PV, SourceType.PV, SourceType.PARAM],
            description=["a test pv", "another test PV", "a param, for testing"],
            dataType=[DataType.INT, DataType.STRING, DataType.STRING],
            datasetType=[
                AttributeDatasetType.MONITOR,
                AttributeDatasetType.DETECTOR,
                AttributeDatasetType.POSITION,
            ],
        )
        self.o.extra_attributes.set_value(extra_attributes)
        self.o.on_configure(
            self.context,
            completed_steps,
            steps_to_do,
            part_info,
            generator=MagicMock(duration=1.0, size=steps_to_do),
            fileDir="/tmp",
        )
        assert self.child.handled_requests.mock_calls == [
            call.put("arrayCallbacks", True),
            call.put("arrayCounter", completed_steps),
            call.put("autoPixelsPerBuffer", "Manual"),
            call.put("binsInSpectrum", 2048),
            call.put("collectMode", "MCA mapping"),
            call.put("ignoreGate", "No"),
            call.put("inputLogicPolarity", "Normal"),
            call.put("pixelAdvanceMode", "Gate"),
            call.put("pixelsPerBuffer", 1),
            call.put("pixelsPerRun", steps_to_do),
            call.put("presetMode", "No preset"),
            call.put("attributesFile", "Z:\\mri-attributes.xml"),
            call.post("start"),
            call.when_value_matches("acquiring", True, None),
        ]
        with open("/tmp/mri-attributes.xml") as f:
            actual_xml = f.read().replace(">", ">\n")

        actual_tree = ElementTree.XML(actual_xml)
        expected_tree = ElementTree.XML(expected_xml)
        assert ElementTree.dump(actual_tree) == ElementTree.dump(expected_tree)
