
from malcolm.testutil import ChildTestCase

from malcolm.core import Context, Process
from malcolm.modules.pmac.parts import BeamSelectorPart
from malcolm.yamlutil import make_block_creator

from scanpointgenerator import CompoundGenerator, \
    StaticPointGenerator

import pytest
from mock import call

class TestBeamSelectorPart(ChildTestCase):
    def setUp(self):
        self.process = Process("Process")
        self.context = Context(self.process)
        pmac_block = make_block_creator(
            __file__, "test_pmac_manager_block.yaml")
        self.child = self.create_child_block(
            pmac_block, self.process, mri_prefix="PMAC",
            config_dir="/tmp")
        # These are the child blocks we are interested in
        self.child_x = self.process.get_controller(
            "BL45P-ML-STAGE-01:X")
        #self.child_y = self.process.get_controller(
        #    "BL45P-ML-STAGE-01:Y")
        self.child_cs1 = self.process.get_controller("PMAC:CS1")
        self.child_traj = self.process.get_controller("PMAC:TRAJ")
        self.child_status = self.process.get_controller("PMAC:STATUS")

        # CS1 needs to have the right port otherwise we will error
        self.set_attributes(self.child_cs1, port="CS1")
        self.o = BeamSelectorPart(name="beamSelector",
                                  mri="PMAC",
                                  selectorAxis="x",
                                  startAngle=0,
                                  endAngle=0.5)
        self.context.set_notify_dispatch_request(
            self.o.notify_dispatch_request)
        self.process.start()

        pass

    def tearDown(self):
        del self.context
        self.process.stop(timeout=1)
        pass

    def set_motor_attributes(self,
                             x_pos=0.5,
                             units="deg",
                             x_acceleration=4,
                             x_velocity=10):
        # create some parts to mock
        # the motion controller and an axis in a CS
        self.set_attributes(
            self.child_x, cs="CS1,A",
            accelerationTime=x_velocity / x_acceleration,
            resolution=0.001,
            offset=0.0, maxVelocity=x_velocity, readback=x_pos,
            velocitySettle=0.0, units=units)

    def test_configure_single_rotation(self):
        self.set_motor_attributes()
        nRotations = 1
        generator = CompoundGenerator(
            [StaticPointGenerator(nRotations)], [], [], duration=1)
        generator.prepare()
        self.o.configure(self.context, 0, nRotations, {}, generator, [])


        assert self.child.handled_requests.mock_calls == [
            call.post('writeProfile',
                      csPort='CS1', timeArray=[0.002], userPrograms=[8]),
            call.post('executeProfile'),
            call.post('moveCS1', a=-0.1,
                      moveTime=pytest.approx(0.692, abs=1e-3)),
            # pytest.approx to allow sensible compare with numpy arrays
            call.post('writeProfile',
                      a=pytest.approx([0.0, 0.250, 0.500, 0.600]),
                      csPort='CS1',
                      timeArray=pytest.approx([
                          200000, 250000, 250000,
                          200000]),
                      userPrograms=pytest.approx([
                          1, 4, 2, 8]),
                      velocityMode=pytest.approx([
                          1, 0, 1, 3]))
        ]
        assert self.o.completed_steps_lookup == [
            0, 0, 1, 1]

    def test_configure_cycle(self):
        self.set_motor_attributes()
        nRotations = 2
        generator = CompoundGenerator(
            [StaticPointGenerator(nRotations)], [], [], duration=1)
        generator.prepare()
        self.o.configure(self.context, 0, nRotations, {}, generator,
                         [])

        assert self.child.handled_requests.mock_calls == [
            call.post('writeProfile',
                      csPort='CS1', timeArray=[0.002],
                      userPrograms=[8]),
            call.post('executeProfile'),
            call.post('moveCS1', a=-0.1,
                      moveTime=pytest.approx(0.692, abs=1e-3)),
            # pytest.approx to allow sensible compare with numpy arrays
            call.post('writeProfile',
                      a=pytest.approx([0.0, 0.25, 0.5, 0.6, 0.6,
                                       0.5, 0.25, 0.0, -0.1]),
                      csPort='CS1',
                      timeArray=pytest.approx([
                          200000, 250000, 250000,
                          200000, 100000, 200000,
                          250000, 250000,
                          200000]),
                      userPrograms=pytest.approx([
                          1, 4, 2, 8, 8, 1, 4, 2, 8]),
                      velocityMode=pytest.approx([
                          1, 0, 1, 1, 1, 1, 0, 1, 3]))
        ]
        assert self.o.completed_steps_lookup == [
            0, 0, 1, 1, 1, 1, 1, 2, 2]

    def test_validate(self):
        generator = CompoundGenerator([StaticPointGenerator(2)],
                                      [], [], 0.0102)
        axesToMove = ["x"]
        # servoFrequency() return value
        self.child.handled_requests.post.return_value = 4919.300698316487
        ret = self.o.validate(self.context, generator, axesToMove,
                              {})
        expected = 0.010166
        assert ret.value.duration == expected

    def test_critical_exposure(self):
        self.set_motor_attributes()
        nRotations = 2
        generator = CompoundGenerator(
            [StaticPointGenerator(nRotations)], [], [], duration=0.5)
        generator.prepare()
        self.o.configure(self.context, 0, nRotations, {}, generator,
                         [])

        assert self.child.handled_requests.mock_calls == [
            call.post('writeProfile',
                      csPort='CS1', timeArray=[0.002],
                      userPrograms=[8]),
            call.post('executeProfile'),
            call.post('moveCS1', a=-0.1,
                      moveTime=pytest.approx(0.692, abs=1e-3)),
            # pytest.approx to allow sensible compare with numpy arrays
            call.post('writeProfile',
                      a=pytest.approx([0.0, 0.25, 0.5, 0.6,
                                       0.5, 0.25, 0.0, -0.1]),
                      csPort='CS1',
                      timeArray=pytest.approx([
                          200000, 250000, 250000,
                          200000, 200000,
                          250000, 250000,
                          200000]),
                      userPrograms=pytest.approx([
                          1, 4, 2, 8, 1, 4, 2, 8]),
                      velocityMode=pytest.approx([
                          1, 0, 1, 1, 1, 0, 1, 3]))
        ]