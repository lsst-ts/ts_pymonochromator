# This file is part of ts_atmonochromator.
#
# Developed for the LSST Telescope and Site System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

import sys
import unittest
import asyncio
import numpy as np
import logging

from lsst.ts import salobj

from lsst.ts.monochromator import monochromator_csc as csc
from lsst.ts.monochromator import MockMonochromatorController

import SALPY_ATMonochromator

np.random.seed(12)

index_gen = salobj.index_generator()

logger = logging.getLogger()
logger.level = logging.DEBUG


class Harness:
    def __init__(self):
        salobj.test_utils.set_random_lsst_dds_domain()
        self.csc = csc.CSC()
        self.remote = salobj.Remote(SALPY_ATMonochromator)
        self.mock_ctrl = MockMonochromatorController(port=self.csc.model.port)


class TestATMonochromatorCSC(unittest.TestCase):

    def test_standard_state_transitions(self):
        """Test standard CSC state transitions.

        The initial state is STANDBY.
        The standard commands and associated state transitions are:

        * enterControl: OFFLINE to STANDBY
        * start: STANDBY to DISABLED
        * enable: DISABLED to ENABLED

        * disable: ENABLED to DISABLED
        * standby: DISABLED to STANDBY
        * exitControl: STANDBY, FAULT to OFFLINE (quit)
        """

        async def doit():

            commands = ("start", "enable", "disable", "exitControl", "standby")
            harness = Harness()
            await asyncio.wait_for(harness.mock_ctrl.start(), timeout=2)

            # Check initial state
            current_state = await harness.remote.evt_summaryState.next(flush=False, timeout=1.)

            self.assertEqual(harness.csc.summary_state, salobj.State.STANDBY)
            self.assertEqual(current_state.summaryState, salobj.State.STANDBY)

            # Check that settingVersions was published and matches expected values
            setting_versions = await harness.remote.evt_settingVersions.next(flush=False, timeout=1.)
            self.assertEqual(setting_versions.recommendedSettingsVersion,
                             harness.csc.model.config['settingVersions']['recommendedSettingsVersion'])
            self.assertEqual(setting_versions.recommendedSettingsLabels,
                             harness.csc.model.settings_labels)
            self.assertTrue(setting_versions.recommendedSettingsVersion in
                            setting_versions.recommendedSettingsLabels.split(','))
            self.assertTrue('simulation' in
                            setting_versions.recommendedSettingsLabels.split(','))

            for bad_command in commands:
                if bad_command in ("start", "exitControl"):
                    continue  # valid command in STANDBY state
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with self.assertRaises(salobj.AckError):
                        await cmd_attr.start(cmd_attr.DataType(), timeout=1.)

            # send start; new state is DISABLED
            cmd_attr = getattr(harness.remote, f"cmd_start")
            state_coro = harness.remote.evt_summaryState.next(flush=True, timeout=1.)
            cmd_attr.set(settingsToApply='simulation')  # user simulation setting.
            await cmd_attr.start(timeout=120)  # this one can take longer to execute
            state = await state_coro
            self.assertEqual(harness.csc.summary_state, salobj.State.DISABLED)
            self.assertEqual(state.summaryState, salobj.State.DISABLED)

            for bad_command in commands:
                if bad_command in ("enable", "standby"):
                    continue  # valid command in DISABLED state
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with self.assertRaises(salobj.AckError):
                        await cmd_attr.start(cmd_attr.DataType(), timeout=1.)

            # send enable; new state is ENABLED
            cmd_attr = getattr(harness.remote, f"cmd_enable")
            state_coro = harness.remote.evt_summaryState.next(flush=True, timeout=1.)
            try:
                # enable may take some time to complete
                await cmd_attr.start(cmd_attr.DataType(), timeout=120.)
            finally:
                state = await state_coro
            self.assertEqual(harness.csc.summary_state, salobj.State.ENABLED)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)

            for bad_command in commands:
                if bad_command in ("disable",):
                    continue  # valid command in ENABLE state
                logger.debug(f"Testing {bad_command}")
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with self.assertRaises(salobj.AckError):
                        await cmd_attr.start(cmd_attr.DataType(), timeout=1.)

            # send disable; new state is DISABLED
            cmd_attr = getattr(harness.remote, f"cmd_disable")
            # this CMD may take some time to complete
            await cmd_attr.start(cmd_attr.DataType(), timeout=30.)
            self.assertEqual(harness.csc.summary_state, salobj.State.DISABLED)

            await harness.mock_ctrl.stop()

        stream_handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(stream_handler)

        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == '__main__':
    unittest.main()
