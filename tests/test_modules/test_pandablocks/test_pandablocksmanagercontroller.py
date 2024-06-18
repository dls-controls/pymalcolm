import shutil
import unittest
from collections import OrderedDict

from mock import ANY, patch

from malcolm.core import AlarmSeverity, Process, Queue, Subscribe
from malcolm.modules.builtin.defines import tmp_dir
from malcolm.modules.pandablocks.controllers import PandAManagerController
from malcolm.modules.pandablocks.pandablocksclient import BlockData, FieldData
from malcolm.modules.pandablocks.util import BitsTable, PositionCapture


class PandABlocksManagerControllerTest(unittest.TestCase):
    @patch(
        "malcolm.modules.pandablocks.controllers."
        "pandamanagercontroller.PandABlocksClient"
    )
    def setUp(self, mock_client):
        self.process = Process()
        self.config_dir = tmp_dir("config_dir")
        self.o = PandAManagerController(
            mri="P", config_dir=self.config_dir.value, poll_period=1000
        )
        self.client = self.o._client
        self.client.started = False
        blocks_data = OrderedDict()
        fields = OrderedDict()
        fields["INP"] = FieldData("pos_mux", "", "Input A", ["ZERO", "COUNTER.OUT"])
        fields["START"] = FieldData("param", "", "Start position", [])
        fields["STEP"] = FieldData("param", "", "Step position", [])
        fields["OUT"] = FieldData("bit_out", "", "Output", [])
        blocks_data["PCOMP"] = BlockData(1, "Position Compare", fields)
        fields = OrderedDict()
        fields["INP"] = FieldData("bit_mux", "", "Input", ["ZERO", "TTLIN.VAL"])
        fields["START"] = FieldData("param", "pos", "Start position", [])
        fields["OUT"] = FieldData("pos_out", "", "Output", ["No", "Capture"])
        blocks_data["COUNTER"] = BlockData(1, "", fields)
        fields = OrderedDict()
        fields["VAL"] = FieldData("bit_out", "", "Output", [])
        blocks_data["TTLIN"] = BlockData(2, "", fields)
        blocks_data["PCAP"] = BlockData(1, "", {})
        self.client.get_blocks_data.return_value = blocks_data
        changes = [
            ["PCOMP.INP", "ZERO"],
            ["PCOMP.STEP", "0"],
            ["PCOMP.START", "0"],
            ["PCOMP.OUT", "0"],
            ["COUNTER.INP", "ZERO"],
            ["COUNTER.INP.DELAY", "0"],
            ["COUNTER.OUT", "0"],
            ["COUNTER.OUT.SCALE", "1"],
            ["COUNTER.OUT.OFFSET", "0"],
            ["COUNTER.OUT.UNITS", ""],
            ["TTLIN1.VAL", "0"],
            ["TTLIN2.VAL", "0"],
            ["*METADATA.LAYOUT", ""],
        ]
        self.client.get_changes.return_value = changes
        pcap_bit_fields = {
            "PCAP.BITS0.CAPTURE": ["TTLIN1.VAL", "TTLIN2.VAL", "PCOMP.OUT", ""]
        }
        self.client.get_pcap_bits_fields.return_value = pcap_bit_fields
        self.process.add_controller(self.o)
        self.process.start()

    def tearDown(self):
        self.process.stop()
        shutil.rmtree(self.config_dir.value)

    def test_no_connection(self):
        o = PandAManagerController(
            mri="MRI",
            config_dir=self.config_dir.value,
            hostname="non-existant-hostname",
        )
        self.process.add_controller(o)
        health = self.process.block_view("MRI").health
        assert (
            health.value == "Can't connect to 'non-existant-hostname:8888', "
            "did all services on the PandA start correctly?"
        )
        assert health.alarm.severity == AlarmSeverity.MAJOR_ALARM

    def test_initial_changes(self):
        assert self.process.mri_list == [
            "P",
            "P:PCOMP",
            "P:COUNTER",
            "P:TTLIN1",
            "P:TTLIN2",
            "P:PCAP",
        ]
        assert self.o._bit_outs == {
            "TTLIN1.VAL": False,
            "TTLIN2.VAL": False,
            "PCOMP.OUT": False,
        }
        pcomp = self.process.block_view("P:PCOMP")
        counter = self.process.block_view("P:COUNTER")
        ttlin = self.process.block_view("P:TTLIN1")
        assert pcomp.inp.value == "ZERO"
        assert pcomp.start.value == 0.0
        assert pcomp.step.value == 0.0
        assert pcomp.out.value is False
        assert counter.inp.value == "ZERO"
        assert counter.inpDelay.value == 0
        assert counter.out.value == 0.0
        assert ttlin.val.value is False

    def test_toggling_bit_outs(self):
        ttlin = self.process.block_view("P:TTLIN1")
        assert ttlin.val.value is False

        # Change to a different value, should change once and stick
        self.o.handle_changes([("TTLIN1.VAL", "1")])
        assert ttlin.val.value is True
        self.o.handle_changes(())
        assert ttlin.val.value is True
        self.o.handle_changes(())
        assert ttlin.val.value is True

        # Change to same value, should toggle once
        self.o.handle_changes([("TTLIN1.VAL", "1")])
        assert ttlin.val.value is False
        self.o.handle_changes(())
        assert ttlin.val.value is True
        self.o.handle_changes(())
        assert ttlin.val.value is True

        # Change back, should change once and stick
        self.o.handle_changes([("TTLIN1.VAL", "0")])
        assert ttlin.val.value is False
        self.o.handle_changes(())
        assert ttlin.val.value is False
        self.o.handle_changes(())
        assert ttlin.val.value is False

        # Change to same value, should toggle once
        self.o.handle_changes([("TTLIN1.VAL", "0")])
        assert ttlin.val.value is True
        self.o.handle_changes(())
        assert ttlin.val.value is False
        self.o.handle_changes(())
        assert ttlin.val.value is False

        # Change to same value, then get the opposite next tick
        self.o.handle_changes([("TTLIN1.VAL", "0")])
        assert ttlin.val.value is True
        self.o.handle_changes([("TTLIN1.VAL", "1")])
        assert ttlin.val.value is False
        self.o.handle_changes(())
        assert ttlin.val.value is True
        self.o.handle_changes(())
        assert ttlin.val.value is True

    def test_constant_toggling_bit_outs(self):
        ttlin = self.process.block_view("P:TTLIN1")
        assert ttlin.val.value is False

        # Constant updates, should toggle each time
        self.o.handle_changes([("TTLIN1.VAL", "0")])
        assert ttlin.val.value is True
        self.o.handle_changes([("TTLIN1.VAL", "1")])
        assert ttlin.val.value is False
        self.o.handle_changes([("TTLIN1.VAL", "1")])
        assert ttlin.val.value is True
        self.o.handle_changes([("TTLIN1.VAL", "1")])
        assert ttlin.val.value is False
        self.o.handle_changes([("TTLIN1.VAL", "1")])
        assert ttlin.val.value is True
        self.o.handle_changes([("TTLIN1.VAL", "0")])
        assert ttlin.val.value is False
        self.o.handle_changes([("TTLIN1.VAL", "0")])
        assert ttlin.val.value is True
        self.o.handle_changes([("TTLIN1.VAL", "1")])
        assert ttlin.val.value is False
        self.o.handle_changes([("TTLIN1.VAL", "0")])
        assert ttlin.val.value is True
        self.o.handle_changes(())
        assert ttlin.val.value is False
        self.o.handle_changes(())
        assert ttlin.val.value is False

    def test_table_deltas(self):
        queue = Queue()
        subscribe = Subscribe(path=["P"], delta=True)
        subscribe.set_callback(queue.put)
        self.o.handle_request(subscribe)
        delta = queue.get()
        table = delta.changes[0][1]["bits"]["value"]
        assert table.name == ["TTLIN1.VAL", "TTLIN2.VAL", "PCOMP.OUT"]
        assert table.value == [False, False, False]
        assert table.capture == [False, False, False]

        self.o.handle_changes([("TTLIN1.VAL", "1")])
        delta = queue.get()
        assert delta.changes == [
            [["bits", "value", "value"], [True, False, False]],
            [["bits", "timeStamp"], ANY],
        ]

    def test_pos_table_deltas(self):
        queue = Queue()
        subscribe = Subscribe(path=["P"], delta=True)
        subscribe.set_callback(queue.put)
        self.o.handle_request(subscribe)
        delta = queue.get()
        capture_enums = delta.changes[0][1]["positions"]["meta"]["elements"]["capture"][
            "choices"
        ]
        assert capture_enums[0] == PositionCapture.NO
        table = delta.changes[0][1]["positions"]["value"]
        assert table.name == ["COUNTER.OUT"]
        assert table.value == [0.0]
        assert table.scale == [1.0]
        assert table.offset == [0.0]
        assert table.capture == [PositionCapture.NO]

        self.o.handle_changes([("COUNTER.OUT", "20")])
        delta = queue.get()
        assert delta.changes == [
            [["positions", "value", "value"], [20.0]],
            [["positions", "timeStamp"], ANY],
        ]

        self.o.handle_changes([("COUNTER.OUT", "5"), ("COUNTER.OUT.SCALE", 0.5)])
        delta = queue.get()
        assert delta.changes == [
            [["positions", "value", "value"], [2.5]],
            [["positions", "value", "scale"], [0.5]],
            [["positions", "timeStamp"], ANY],
        ]

    def test_change_pcap_bits(self):
        b = self.process.block_view("P")
        assert b.bits.value.capture == [False, False, False]
        b.bits.put_value(BitsTable(name=["TTLIN1.VAL"], value=[False], capture=[True]))
        assert b.bits.value.capture == [True, False, False]
        self.client.set_fields.assert_called_once_with({"PCAP.BITS0.CAPTURE": "Value"})
        self.client.set_fields.reset_mock()
        self.o.handle_changes([("PCAP.BITS0.CAPTURE", "Value")])
        assert b.bits.value.capture == [True, True, True]
        b.bits.put_value(BitsTable(name=["TTLIN1.VAL"], value=[False], capture=[False]))
        assert b.bits.value.capture == [False, True, True]
        self.client.set_fields.assert_called_once_with({"PCAP.BITS0.CAPTURE": "No"})
        self.o.handle_changes([("PCAP.BITS0.CAPTURE", "No")])
        assert b.bits.value.capture == [False, False, False]

    def test_label_change(self):
        pcomp = self.process.block_view("P:PCOMP")
        assert pcomp.label.value == "Position Compare"
        self.o.handle_changes([("*METADATA.LABEL_PCOMP1", "New Label")])
        assert pcomp.label.value == "New Label"
        pcomp.label.put_value("Very new")
        self.client.set_field.assert_called_once_with(
            "*METADATA", "LABEL_PCOMP1", "Very new"
        )

    def test_layout(self):
        panda = self.process.block_view("P")
        layout = panda.layout.value
        assert layout.name == ["PCOMP", "COUNTER", "TTLIN1", "TTLIN2", "PCAP"]
        assert layout.x == [0.0, 0.0, 0.0, 0.0, 0.0]
        assert layout.y == [0.0, 0.0, 0.0, 0.0, 0.0]
        assert layout.visible == [False, False, False, False, False]
        # Change coming from PandA with an extra block in it
        self.o.handle_changes(
            [
                (
                    "*METADATA.LAYOUT",
                    [
                        '{"COUNTER": {"x": 1.2, "y": 2.3},',
                        '"HDF": {"x": 3.5, "y": 4.1}}',
                    ],
                )
            ]
        )
        layout = panda.layout.value
        assert layout.name == ["PCOMP", "COUNTER", "TTLIN1", "TTLIN2", "PCAP"]
        assert layout.x == [0.0, 1.2, 0.0, 0.0, 0.0]
        assert layout.y == [0.0, 2.3, 0.0, 0.0, 0.0]
        assert layout.visible == [False, True, False, False, False]
        # Change coming from Malcolm
        layout = panda.layout.value
        layout.visible = [False, True, True, False, False]
        layout.y = [0.0, 2.3, 5.6, 0.0, 0.0]
        panda.layout.put_value(layout)
        self.client.set_table.assert_called_once_with(
            "*METADATA",
            "LAYOUT",
            [
                '{"COUNTER": {"x": 1.2, "y": 2.3},',
                '"HDF": {"x": 3.5, "y": 4.1},',
                '"TTLIN1": {"x": 0.0, "y": 5.6}}',
            ],
        )
