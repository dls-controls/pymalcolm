import glob
import os
from datetime import datetime
from shutil import copy, rmtree
from tempfile import mkdtemp

import h5py
import numpy as np
from mock import MagicMock, call
from scanpointgenerator import CompoundGenerator, LineGenerator, SquashingExcluder

from malcolm.core import BadValueError, Context, Process
from malcolm.modules.ADOdin.blocks import odin_writer_block
from malcolm.modules.ADOdin.parts import OdinWriterPart
from malcolm.modules.ADOdin.parts.odinwriterpart import greater_than_zero
from malcolm.testutil import ChildTestCase


class TestOdinWriterPart(ChildTestCase):
    def setUp(self):
        self.process = Process("Process")
        self.context = Context(self.process)
        self.child = self.create_child_block(
            odin_writer_block, self.process, mri="mri", prefix="prefix"
        )
        self.mock_when_value_matches(self.child)
        # set up some values for OdinData PVs that Excalibur would have
        settings = {
            "imageHeight": 1536,
            "imageWidth": 1048,
            "blockSize": 1,
            "numProcesses": 4,
            "dataType": "uint16",
        }
        self.set_attributes(self.child, **settings)
        self.o = OdinWriterPart(name="m", mri="mri")
        self.context.set_notify_dispatch_request(self.o.notify_dispatch_request)
        self.process.start()

        self.completed_steps = 0
        # goal for these is 3000, 2000, True
        cols, rows, alternate = 3000, 2000, False
        self.steps_to_do = cols * rows
        xs = LineGenerator("x", "mm", 0.0, 0.5, cols, alternate=alternate)
        ys = LineGenerator("y", "mm", 0.0, 0.1, rows)
        self.generator = CompoundGenerator([ys, xs], [], [], 0.1)
        self.generator.prepare()

    def tearDown(self):
        self.process.stop(timeout=1)

    def test_configure(self):
        tmp_dir = mkdtemp() + os.path.sep
        vds_file = "odin2"

        start_time = datetime.now()
        self.o.on_configure(
            self.context,
            self.completed_steps,
            self.steps_to_do,
            generator=self.generator,
            fileDir=tmp_dir,
            formatName=vds_file,
        )
        assert self.child.handled_requests.mock_calls == [
            call.put("fileName", "odin2_raw_data"),
            call.put("filePath", tmp_dir),
            call.put("numCapture", self.steps_to_do),
            call.post("start"),
            call.when_value_matches("numCaptured", greater_than_zero, None),
        ]
        print(self.child.handled_requests.mock_calls)
        print(
            "OdinWriter configure {} points took {} secs".format(
                self.steps_to_do, datetime.now() - start_time
            )
        )
        rmtree(tmp_dir)

    def test_run(self):
        tmp_dir = mkdtemp() + os.path.sep
        self.o.on_configure(
            self.context,
            self.completed_steps,
            self.steps_to_do,
            generator=self.generator,
            fileDir=tmp_dir,
            formatName="odin2",
            fileTemplate="a_unique_name_%s_from_gda.h5",
        )
        self.child.handled_requests.reset_mock()
        self.o.registrar = MagicMock()
        # run waits for this value
        self.child.field_registry.get_field("numCaptured").set_value(
            self.o.done_when_reaches
        )
        self.o.on_run(self.context)
        assert self.child.handled_requests.mock_calls == [
            call.when_value_matches("numCaptured", self.steps_to_do, None)
        ]
        assert self.o.registrar.report.called_once
        assert self.o.registrar.report.call_args_list[0][0][0].steps == self.steps_to_do
        rmtree(tmp_dir)

    def test_alternate_fails_unless_squashed(self):
        tmp_dir = mkdtemp() + os.path.sep
        cols, rows, alternate = 3000, 2000, True
        self.steps_to_do = cols * rows
        xs = LineGenerator("x", "mm", 0.0, 0.5, cols, alternate=alternate)
        ys = LineGenerator("y", "mm", 0.0, 0.1, rows)
        self.generator = CompoundGenerator([ys, xs], [], [], 0.1)
        self.generator.prepare()

        with self.assertRaises(BadValueError):
            self.o.on_configure(
                self.context,
                self.completed_steps,
                self.steps_to_do,
                generator=self.generator,
                fileDir=tmp_dir,
                formatName="odin3",
            )

        self.generator = CompoundGenerator(
            [ys, xs], [SquashingExcluder(axes=["x", "y"])], [], 0.1
        )
        self.generator.prepare()
        self.o.on_configure(
            self.context,
            self.completed_steps,
            self.steps_to_do,
            generator=self.generator,
            fileDir=tmp_dir,
            formatName="odin2",
        )

    def test_post_run_armed(self):
        self.o.done_when_reaches = 100
        self.o.on_post_run_armed(self.context, steps_to_do=100)
        assert self.o.done_when_reaches == 200

    @staticmethod
    def make_test_data():
        for i in range(6):
            value = i + 1
            f_num = i % 4 + 1
            idx = int(i / 4)
            name = "/data/odin123_raw_data_{:06d}.h5".format(f_num)
            print("updating index {} in file {} with value {}".format(idx, name, value))
            raw = h5py.File(name, "r+", libver="latest")

            # set values in the data
            print(raw.items())
            print(raw["data"][idx])
            data = np.full((1536, 2048), value, np.uint16)
            raw["data"][idx] = data
            raw.close()

    def test_excalibur_vds(self):
        """
        The HDF data for this test was created by running a 6 point scan
        and then using the function make_test_data above to fill each frame
        with its own (1 based) index
        """
        tmp_dir = mkdtemp() + os.path.sep
        test_data = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data/*")
        for f in glob.glob(test_data):
            copy(f, tmp_dir)

        # Create a generator to match the test data
        xs = LineGenerator("x", "mm", 0.0, 4.0, 3)
        ys = LineGenerator("y", "mm", 0.0, 4.0, 2)
        compound = CompoundGenerator([ys, xs], [], [])
        compound.prepare()

        # Call configure to create the VDS
        # This should work with relative paths but doesn't due to VDS bug
        self.o.on_configure(
            self.context,
            0,
            6,
            compound,
            formatName="odin123",
            fileDir=tmp_dir,
            fileTemplate="%s.h5",
        )

        # Open the created VDS file and dataset to check values
        vds_path = os.path.join(tmp_dir, "odin123.h5")
        vds_file = h5py.File(vds_path, "r")
        detector_dataset = vds_file["/entry/detector/data"]

        # Check values at indices 0,0
        self.assertEqual(detector_dataset[0][0][756][393], 1)
        self.assertEqual(detector_dataset[0][0][756][394], 1)
        self.assertEqual(detector_dataset[0][0][756][395], 1)
        self.assertEqual(detector_dataset[0][0][756][396], 1)

        # Change first index
        self.assertEqual(detector_dataset[1][0][756][393], 4)
        self.assertEqual(detector_dataset[1][0][756][394], 4)
        self.assertEqual(detector_dataset[1][0][756][395], 4)
        self.assertEqual(detector_dataset[1][0][756][396], 4)

        # Change second index
        self.assertEqual(detector_dataset[0][2][756][393], 3)
        self.assertEqual(detector_dataset[0][2][756][394], 3)
        self.assertEqual(detector_dataset[0][2][756][395], 3)
        self.assertEqual(detector_dataset[0][2][756][396], 3)

        # Todo there are no gaps in my test data at present:-
        #  update the test data with Alans Gap fill and fix this
        # # Check some values near the bottom of image to ensure
        # # the gaps are there
        # assert detector_dataset[0][0][1685][1521] == 3
        # assert detector_dataset[1][0][1685][1521] == 131
        #
        # assert detector_dataset[0][0][1516][329] == 109
        # assert detector_dataset[0][1][1516][329] == 136
        #
        # # Check some values in the gaps
        # assert detector_dataset[0][0][395][1202] == 0
        # assert detector_dataset[1][0][395][1202] == 0

        # Check detector attributes
        detector_group = vds_file["/entry/detector"]
        for a, b in zip(detector_group.attrs["axes"], ["y_set", "x_set", ".", "."]):
            assert a == b
        assert detector_group.attrs["signal"] == "data"
        assert detector_group.attrs["y_set_indices"] == 0
        assert detector_group.attrs["x_set_indices"] == 1

        # Check _set datasets
        # N.B. units are encoded as ASCII in the original file, so come
        # back as type byte in Python 3
        stage1_x_set_dataset = vds_file["/entry/detector/x_set"]
        assert stage1_x_set_dataset[0] == 0
        assert stage1_x_set_dataset[1] == 2
        assert str(stage1_x_set_dataset.attrs["units"]) == "mm"

        stage1_y_set_dataset = vds_file["/entry/detector/y_set"]
        assert stage1_y_set_dataset[0] == 0
        assert stage1_y_set_dataset[1] == 4
        assert str(stage1_y_set_dataset.attrs["units"]) == "mm"

        vds_file.close()
        rmtree(tmp_dir)
