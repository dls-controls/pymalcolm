import os
from xml.etree import ElementTree

import cothread
from mock import MagicMock, call
from scanpointgenerator import CompoundGenerator, LineGenerator, SpiralGenerator

from malcolm.core import Context, Future, Process
from malcolm.modules.ADCore.blocks import hdf_writer_block
from malcolm.modules.ADCore.infos import (
    CalculatedNDAttributeDatasetInfo,
    FilePathTranslatorInfo,
    NDArrayDatasetInfo,
    NDAttributeDatasetInfo,
)
from malcolm.modules.ADCore.parts import HDFWriterPart
from malcolm.modules.ADCore.parts.hdfwriterpart import greater_than_zero
from malcolm.modules.ADCore.util import AttributeDatasetType
from malcolm.modules.scanning.controllers import RunnableController
from malcolm.modules.scanning.util import DatasetType
from malcolm.testutil import ChildTestCase

expected_xml = (
    '<?xml version="1.0" ?>\n'
    '<hdf5_layout auto_ndattr_default="false">\n'
    '<group name="entry">\n'
    '<attribute name="NX_class" source="constant" type="string" value="NXentry" />\n'
    '<group name="detector">\n'
    '<attribute name="signal" source="constant" type="string" value="detector" />\n'
    '<attribute name="axes" source="constant" type="string" '
    'value="energy_set,.,.,." />\n'
    '<attribute name="NX_class" source="constant" type="string" value="NXdata" />\n'
    '<attribute name="energy_set_indices" source="constant" type="string" '
    'value="0" />\n'
    '<dataset name="energy_set" source="constant" type="float" value="13,15.2">\n'
    '<attribute name="units" source="constant" type="string" value="kEv" />\n'
    "</dataset>\n"
    '<attribute name="x_set_indices" source="constant" type="string" value="1" />\n'
    '<dataset name="x_set" source="constant" type="float" '
    'value="0.473264298891,-1.28806365331,-1.11933765723,0.721339144968,2.26130106714,'
    "2.3717213098,1.08574712174,-0.863941392256,-2.59791589857,-3.46951769442,"
    "-3.22399679412,-1.98374931946,-0.132541097885,1.83482458567,3.45008680308,"
    '4.36998121172,4.42670524204,3.63379270355,2.15784413199,0.269311496406">\n'
    '<attribute name="units" source="constant" type="string" value="mm" />\n'
    "</dataset>\n"
    '<attribute name="y_set_indices" source="constant" type="string" value="1" />\n'
    '<dataset name="y_set" source="constant" type="float" value="-0.64237113553,'
    "-0.500750778455,1.38930992616,1.98393756064,0.784917470231,-1.17377831157,"
    "-2.66405897615,-2.9669684623,-2.01825893141,-0.24129368636,1.72477821509,"
    "3.27215424484,3.98722048131,3.71781556747,2.5610299588,0.799047653518,"
    '-1.18858453138,-3.01284626565,-4.34725663835,-4.9755042398">\n'
    '<attribute name="units" source="constant" type="string" value="mm" />\n'
    "</dataset>\n"
    '<dataset det_default="true" name="detector" source="detector">\n'
    '<attribute name="NX_class" source="constant" type="string" value="SDS" />\n'
    "</dataset>\n"
    "</group>\n"
    '<group name="sum">\n'
    '<attribute name="signal" source="constant" type="string" value="sum" />\n'
    '<attribute name="axes" source="constant" type="string" '
    'value="energy_set,.,.,." />\n'
    '<attribute name="NX_class" source="constant" type="string" value="NXdata" />\n'
    '<attribute name="energy_set_indices" source="constant" type="string" '
    'value="0" />\n'
    '<hardlink name="energy_set" target="/entry/detector/energy_set" />\n'
    '<attribute name="x_set_indices" source="constant" type="string" value="1" />\n'
    '<hardlink name="x_set" target="/entry/detector/x_set" />\n'
    '<attribute name="y_set_indices" source="constant" type="string" value="1" />\n'
    '<hardlink name="y_set" target="/entry/detector/y_set" />\n'
    '<dataset name="sum" ndattribute="StatsTotal" source="ndattribute" />\n'
    "</group>\n"
    '<group name="I0.data">\n'
    '<attribute name="signal" source="constant" type="string" value="I0.data" />\n'
    '<attribute name="axes" source="constant" type="string" '
    'value="energy_set,.,.,." />\n'
    '<attribute name="NX_class" source="constant" type="string" value="NXdata" />\n'
    '<attribute name="energy_set_indices" source="constant" type="string" '
    'value="0" />\n'
    '<hardlink name="energy_set" target="/entry/detector/energy_set" />\n'
    '<attribute name="x_set_indices" source="constant" type="string" value="1" />\n'
    '<hardlink name="x_set" target="/entry/detector/x_set" />\n'
    '<attribute name="y_set_indices" source="constant" type="string" value="1" />\n'
    '<hardlink name="y_set" target="/entry/detector/y_set" />\n'
    '<dataset name="I0.data" ndattribute="COUNTER1.COUNTER" source="ndattribute" />\n'
    "</group>\n"
    '<group name="It.data">\n'
    '<attribute name="signal" source="constant" type="string" value="It.data" />\n'
    '<attribute name="axes" source="constant" type="string" '
    'value="energy_set,.,.,." />\n'
    '<attribute name="NX_class" source="constant" type="string" value="NXdata" />\n'
    '<attribute name="energy_set_indices" source="constant" type="string" '
    'value="0" />\n'
    '<hardlink name="energy_set" target="/entry/detector/energy_set" />\n'
    '<attribute name="x_set_indices" source="constant" type="string" value="1" />\n'
    '<hardlink name="x_set" target="/entry/detector/x_set" />\n'
    '<attribute name="y_set_indices" source="constant" type="string" value="1" />\n'
    '<hardlink name="y_set" target="/entry/detector/y_set" />\n'
    '<dataset name="It.data" ndattribute="COUNTER2.COUNTER" source="ndattribute" />\n'
    "</group>\n"
    '<group name="t1x.value">\n'
    '<attribute name="signal" source="constant" type="string" value="t1x.value" />\n'
    '<attribute name="axes" source="constant" type="string" '
    'value="energy_set,.,.,." />\n'
    '<attribute name="NX_class" source="constant" type="string" value="NXdata" />\n'
    '<attribute name="energy_set_indices" source="constant" type="string" '
    'value="0" />\n'
    '<hardlink name="energy_set" target="/entry/detector/energy_set" />\n'
    '<attribute name="x_set_indices" source="constant" type="string" value="1" />\n'
    '<hardlink name="x_set" target="/entry/detector/x_set" />\n'
    '<attribute name="y_set_indices" source="constant" type="string" value="1" />\n'
    '<hardlink name="y_set" target="/entry/detector/y_set" />\n'
    '<dataset name="t1x.value" ndattribute="INENC1.VAL" source="ndattribute" />\n'
    "</group>\n"
    '<group name="NDAttributes" ndattr_default="true">\n'
    '<attribute name="NX_class" source="constant" type="string" '
    'value="NXcollection" />\n'
    '<dataset name="NDArrayUniqueId" ndattribute="NDArrayUniqueId" '
    'source="ndattribute" />\n'
    '<dataset name="NDArrayTimeStamp" ndattribute="NDArrayTimeStamp" '
    'source="ndattribute" />\n'
    "</group>\n"
    "</group>\n"
    "</hdf5_layout>\n"
)

expected_xml_limited_attr = expected_xml.replace(
    '<group name="NDAttributes" ndattr_default="true">',
    '<group name="NDAttributes" ndattr_default="false">',
)


class TestHDFWriterPart(ChildTestCase):
    maxDiff = None

    def setUp(self):
        self.process = Process("Process")
        self.context = Context(self.process)
        self.child = self.create_child_block(
            hdf_writer_block, self.process, mri="BLOCK:HDF5", prefix="prefix"
        )
        self.process.start()

    def tearDown(self):
        self.process.stop(2)

    def test_init(self):
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        c = RunnableController("mri", "/tmp")
        c.add_part(self.o)
        self.process.add_controller(c)
        b = c.block_view()
        assert list(b.configure.meta.takes.elements) == [
            "generator",
            "fileDir",
            "axesToMove",
            "breakpoints",
            "formatName",
            "fileTemplate",
        ]

    def configure_and_check_output(self, on_windows=False):
        energy = LineGenerator("energy", "kEv", 13.0, 15.2, 2)
        spiral = SpiralGenerator(["x", "y"], ["mm", "mm"], [0.0, 0.0], 5.0, scale=2.0)
        generator = CompoundGenerator([energy, spiral], [], [], 0.1)
        generator.prepare()
        fileDir = "/tmp"
        formatName = "xspress3"
        fileTemplate = "thing-%s.h5"
        completed_steps = 0
        steps_to_do = 38
        part_info = {
            "DET": [NDArrayDatasetInfo(2)],
            "PANDA": [
                NDAttributeDatasetInfo.from_attribute_type(
                    "I0", AttributeDatasetType.DETECTOR, "COUNTER1.COUNTER"
                ),
                NDAttributeDatasetInfo.from_attribute_type(
                    "It", AttributeDatasetType.MONITOR, "COUNTER2.COUNTER"
                ),
                NDAttributeDatasetInfo.from_attribute_type(
                    "t1x", AttributeDatasetType.POSITION, "INENC1.VAL"
                ),
            ],
            "STAT": [CalculatedNDAttributeDatasetInfo("sum", "StatsTotal")],
        }
        if on_windows:
            part_info["WINPATH"] = [FilePathTranslatorInfo("Y", "/tmp", "")]
        infos = self.o.on_configure(
            self.context,
            completed_steps,
            steps_to_do,
            part_info,
            generator,
            fileDir,
            formatName,
            fileTemplate,
        )
        assert len(infos) == 8
        assert infos[0].name == "xspress3.data"
        assert infos[0].filename == "thing-xspress3.h5"
        assert infos[0].type == DatasetType.PRIMARY
        assert infos[0].rank == 4
        assert infos[0].path == "/entry/detector/detector"
        assert infos[0].uniqueid == "/entry/NDAttributes/NDArrayUniqueId"

        assert infos[1].name == "xspress3.sum"
        assert infos[1].filename == "thing-xspress3.h5"
        assert infos[1].type == DatasetType.SECONDARY
        assert infos[1].rank == 4
        assert infos[1].path == "/entry/sum/sum"
        assert infos[1].uniqueid == "/entry/NDAttributes/NDArrayUniqueId"

        assert infos[2].name == "I0.data"
        assert infos[2].filename == "thing-xspress3.h5"
        assert infos[2].type == DatasetType.PRIMARY
        assert infos[2].rank == 4
        assert infos[2].path == "/entry/I0.data/I0.data"
        assert infos[2].uniqueid == "/entry/NDAttributes/NDArrayUniqueId"

        assert infos[3].name == "It.data"
        assert infos[3].filename == "thing-xspress3.h5"
        assert infos[3].type == DatasetType.MONITOR
        assert infos[3].rank == 4
        assert infos[3].path == "/entry/It.data/It.data"
        assert infos[3].uniqueid == "/entry/NDAttributes/NDArrayUniqueId"

        assert infos[4].name == "t1x.value"
        assert infos[4].filename == "thing-xspress3.h5"
        assert infos[4].type == DatasetType.POSITION_VALUE
        assert infos[4].rank == 4
        assert infos[4].path == "/entry/t1x.value/t1x.value"
        assert infos[4].uniqueid == "/entry/NDAttributes/NDArrayUniqueId"

        assert infos[5].name == "energy.value_set"
        assert infos[5].filename == "thing-xspress3.h5"
        assert infos[5].type == DatasetType.POSITION_SET
        assert infos[5].rank == 1
        assert infos[5].path == "/entry/detector/energy_set"
        assert infos[5].uniqueid == ""

        assert infos[6].name == "x.value_set"
        assert infos[6].filename == "thing-xspress3.h5"
        assert infos[6].type == DatasetType.POSITION_SET
        assert infos[6].rank == 1
        assert infos[6].path == "/entry/detector/x_set"
        assert infos[6].uniqueid == ""

        assert infos[7].name == "y.value_set"
        assert infos[7].filename == "thing-xspress3.h5"
        assert infos[7].type == DatasetType.POSITION_SET
        assert infos[7].rank == 1
        assert infos[7].path == "/entry/detector/y_set"
        assert infos[7].uniqueid == ""

        expected_xml_filename_local = "/tmp/BLOCK_HDF5-layout.xml"
        if on_windows:
            expected_xml_filename_remote = "Y:\\BLOCK_HDF5-layout.xml"
            expected_filepath = "Y:" + os.sep
        else:
            expected_xml_filename_remote = expected_xml_filename_local
            expected_filepath = "/tmp" + os.sep
        # Wait for the start_future so the post gets through to our child
        # even on non-cothread systems
        self.o.start_future.result(timeout=1)
        assert self.child.handled_requests.mock_calls == [
            call.put("positionMode", True),
            call.put("arrayCounter", 0),
            call.put("dimAttDatasets", True),
            call.put("enableCallbacks", True),
            call.put("fileName", "xspress3"),
            call.put("filePath", expected_filepath),
            call.put("fileTemplate", "%sthing-%s.h5"),
            call.put("fileWriteMode", "Stream"),
            call.put("lazyOpen", True),
            call.put("storeAttr", True),
            call.put("swmrMode", True),
            call.put("extraDimSize3", 1),
            call.put("extraDimSize4", 1),
            call.put("extraDimSize5", 1),
            call.put("extraDimSize6", 1),
            call.put("extraDimSize7", 1),
            call.put("extraDimSize8", 1),
            call.put("extraDimSize9", 1),
            call.put("extraDimSizeN", 20),
            call.put("extraDimSizeX", 2),
            call.put("extraDimSizeY", 1),
            call.put("numExtraDims", 1),
            call.put("posNameDim3", ""),
            call.put("posNameDim4", ""),
            call.put("posNameDim5", ""),
            call.put("posNameDim6", ""),
            call.put("posNameDim7", ""),
            call.put("posNameDim8", ""),
            call.put("posNameDim9", ""),
            call.put("posNameDimN", "d1"),
            call.put("posNameDimX", "d0"),
            call.put("posNameDimY", ""),
            call.put("flushAttrPerNFrames", 0),
            call.put("flushDataPerNFrames", 38),
            call.put("xmlLayout", expected_xml_filename_remote),
            call.put("numCapture", 0),
            call.post("start"),
            call.when_value_matches("arrayCounterReadback", greater_than_zero, None),
        ]
        with open(expected_xml_filename_local) as f:
            actual_xml = f.read().replace(">", ">\n")
        # Check the layout filename Malcolm uses for file creation
        assert self.o.layout_filename == expected_xml_filename_local
        return actual_xml

    @staticmethod
    def mock_xml_is_valid_check(part):
        mock_xml_layout_value = MagicMock(name="mock_xml_layout_value")
        mock_xml_layout_value.return_value = True
        part._check_xml_is_valid = mock_xml_layout_value

    def test_configure(self):
        self.mock_when_value_matches(self.child)
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        self.mock_xml_is_valid_check(self.o)
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        actual_xml = self.configure_and_check_output()

        actual_tree = ElementTree.XML(actual_xml)
        expected_tree = ElementTree.XML(expected_xml)
        assert ElementTree.dump(actual_tree) == ElementTree.dump(expected_tree)

    def test_honours_write_all_attributes_flag(self):
        self.mock_when_value_matches(self.child)
        self.o = HDFWriterPart(
            name="m", mri="BLOCK:HDF5", write_all_nd_attributes=False
        )
        self.mock_xml_is_valid_check(self.o)
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        actual_xml = self.configure_and_check_output()

        actual_tree = ElementTree.XML(actual_xml)
        expected_tree = ElementTree.XML(expected_xml)
        assert ElementTree.dump(actual_tree) == ElementTree.dump(expected_tree)

    def test_configure_windows(self):
        self.mock_when_value_matches(self.child)
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5", runs_on_windows=True)
        self.mock_xml_is_valid_check(self.o)
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        actual_xml = self.configure_and_check_output(on_windows=True)

        actual_tree = ElementTree.XML(actual_xml)
        expected_tree = ElementTree.XML(expected_xml)
        assert ElementTree.dump(actual_tree) == ElementTree.dump(expected_tree)

    def test_run(self):
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        self.o.done_when_reaches = 38
        self.o.completed_offset = 0
        # Say that we're getting the first frame
        self.o.array_future = Future(None)
        self.o.array_future.set_result(None)
        self.o.registrar = MagicMock()
        # run waits for this value, so say we have finished immediately
        self.set_attributes(self.child, uniqueId=self.o.done_when_reaches)
        self.mock_when_value_matches(self.child)
        self.o.on_run(self.context)
        assert self.child.handled_requests.mock_calls == [
            call.when_value_matches("uniqueId", 38, None)
        ]
        assert self.o.registrar.report.called_once
        assert self.o.registrar.report.call_args_list[0][0][0].steps == 38

    def test_run_and_flush(self):
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")

        def set_unique_id():
            # Sleep for 2.5 seconds to ensure 2 flushes, and then set value to finish
            cothread.Sleep(2.5)
            self.set_attributes(self.child, uniqueId=self.o.done_when_reaches)

        self.o.done_when_reaches = 38
        self.o.completed_offset = 0
        # Say that we're getting the first frame
        self.o.array_future = Future(None)
        self.o.array_future.set_result(None)
        self.o.start_future = Future(None)
        self.o.registrar = MagicMock()
        self.o.frame_timeout = 60
        # Spawn process to finish it after a few seconds
        self.process.spawn(set_unique_id)
        # Run
        self.o.on_run(self.context)
        assert self.child.handled_requests.mock_calls == [
            call.post("flushNow"),
            call.post("flushNow"),
        ]
        assert self.o.registrar.report.called_once
        assert self.o.registrar.report.call_args_list[0][0][0].steps == 0
        assert self.o.registrar.report.call_args_list[1][0][0].steps == 38

    def test_seek(self):
        self.mock_when_value_matches(self.child)
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        self.o.done_when_reaches = 10
        completed_steps = 4
        steps_to_do = 3
        self.o.on_seek(self.context, completed_steps, steps_to_do)
        assert self.child.handled_requests.mock_calls == [
            call.put("arrayCounter", 0),
            call.when_value_matches("arrayCounterReadback", greater_than_zero, None),
        ]
        assert self.o.done_when_reaches == 13

    def test_post_run_ready(self):
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        # Say that we've returned from start
        self.o.start_future = Future(None)
        self.o.start_future.set_result(None)
        fname = "/tmp/test_filename"
        with open(fname, "w") as f:
            f.write("thing")
        assert os.path.isfile(fname)
        self.o.layout_filename = fname
        self.o.on_post_run_ready(self.context)
        assert self.child.handled_requests.mock_calls == []
        assert os.path.isfile(fname)
        self.o.on_reset(self.context)
        assert not os.path.isfile(fname)

    def test_post_run_ready_not_done_flush(self):
        # Say that we've returned from start
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        self.o.start_future = Future(None)
        fname = "/tmp/test_filename"
        with open(fname, "w") as f:
            f.write("thing")
        assert os.path.isfile(fname)
        self.o.layout_filename = fname
        self.o.on_post_run_ready(self.context)
        assert self.child.handled_requests.mock_calls == [call.post("flushNow")]
        assert os.path.isfile(fname)
        self.o.on_reset(self.context)
        assert not os.path.isfile(fname)

    def test_post_run_armed(self):
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        self.o.done_when_reaches = 100
        self.o.on_post_run_armed(self.context, steps_to_do=100)
        assert self.o.done_when_reaches == 200

    def test_check_xml_is_valid_method_succeeds_for_valid_value(self):
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        child = MagicMock(name="child_mock")
        child.xmlLayoutValid.value = True

        try:
            self.o._check_xml_is_valid(child)
        except AssertionError:
            self.fail("_check_xml_is_valid() threw unexpected AssertionError")

    def test_check_xml_is_valid_method_throws_AssertionError_for_bad_value(self):
        self.o = HDFWriterPart(name="m", mri="BLOCK:HDF5")
        child = MagicMock(name="child_mock")
        child.xmlLayoutValid.value = False
        child.xmlErrorMsg.value = "XML description file cannot be opened"

        self.assertRaises(AssertionError, self.o._check_xml_is_valid, child)
