import os
import sys
from collections import OrderedDict
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import setup_malcolm_paths
import unittest

from malcolm.core.booleanarraymeta import BooleanArrayMeta
from malcolm.core.serializable import Serializable

class TestBooleanArrayMeta(unittest.TestCase):

    def setUp(self):
        self.meta = BooleanArrayMeta("test_meta", "test description")

    def test_init(self):
        self.assertEqual("test_meta", self.meta.name)
        self.assertEqual("test description", self.meta.description)
        self.assertEqual(self.meta.label, "test_meta")
        self.assertEqual(self.meta.typeid, "malcolm:core/BooleanArrayMeta:1.0")

    def test_validate_none(self):
        self.assertIsNone(self.meta.validate(None))

    def test_validate_array(self):
        array = ["True", "", True, False, 1, 0]
        self.assertEquals(
            [True, False, True, False, True, False],
            self.meta.validate(array))

    def test_not_iterable_raises(self):
        value = True
        self.assertRaises(ValueError, self.meta.validate, value)

    def test_null_element_raises(self):
        array = ["test", None]
        self.assertRaises(ValueError, self.meta.validate, array)

    def test_to_dict(self):
        expected = OrderedDict()
        expected["typeid"] = "malcolm:core/BooleanArrayMeta:1.0"
        expected["description"] = "test description"
        expected["tags"] = []
        expected["writeable"] = True
        expected["label"] = "test_meta"
        self.assertEqual(expected, self.meta.to_dict())

    def test_from_dict(self):
        d = OrderedDict()
        d["description"] = "test array description"
        d["tags"] = ["tag"]
        d["writeable"] = False
        d["label"] = "test_label"
        s = BooleanArrayMeta.from_dict("test_array_meta", d)
        self.assertEqual(BooleanArrayMeta, type(s))
        self.assertEqual(s.name, "test_array_meta")
        self.assertEqual(s.description, "test array description")
        self.assertEqual(s.tags, ["tag"])
        self.assertEqual(s.writeable, False)
        self.assertEqual(s.label, "test_label")


if __name__ == "__main__":
    unittest.main()
