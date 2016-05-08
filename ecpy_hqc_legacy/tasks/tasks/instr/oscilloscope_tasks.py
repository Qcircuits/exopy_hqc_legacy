# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright 2015-2016 by EcpyHqcLegacy Authors, see AUTHORS for more details.
#
# Distributed under the terms of the BSD license.
#
# The full license is in the file LICENCE, distributed with this software.
# -----------------------------------------------------------------------------
"""Task to apply a magnetic field.

"""
from __future__ import (division, unicode_literals, print_function,
                        absolute_import)

import numpy as np
from atom.api import (Unicode, Bool, set_default, Enum)
from ecpy.tasks.api import InstrumentTask


class OscilloGetTraceTask(InstrumentTask):
    """ Get the trace displayed on the oscilloscope.

    """
    #: Trace to collect from the oscilloscope
    trace = Enum('1', '2', '3', '4', 'TA', 'TB', 'TC', 'TD').tag(pref=True)

    #: Number of time the instrument should average.
    average_nb = Unicode().tag(pref=True, feval=True)

    #: Should hid=gh resolution be used.
    highres = Bool(True).tag(pref=True)

    database_entries = set_default({'trace_data': np.array([1.0]),
                                    'oscillo_config': ''})

    def perform(self):
        """Get the data from the instrument.

        """
        if self.driver.owner != self.name:
            self.driver.owner = self.name

        channel = self.driver.get_channel(self.trace)
        data = channel.read_data_complete(self.highres)

        msg = 'Coupling {}, Average number {}'
        oscillo_config = msg. format(channel.sweep, data['VERT_COUPLING'])
        self.write_in_database('oscillo_config', oscillo_config)

        # if the TrigArray lentgh is null, it's a simple single sweep waveform
        if data['TRIGTIME_ARRAY'][0] == 0:
            arr = np.rec.fromarrays([data['SingleSweepTimesValuesArray'],
                                     data['Volt_Value_array']],
                                    names=['Time (s)', 'Voltage (V)'])
            self.write_in_database('trace_data', arr)
        else:
            arr = np.rec.fromarrays([data['SEQNCEWaveformTimesValuesArray'],
                                     data['Volt_Value_array']],
                                    names=['Time (s)', 'Voltage (V)'])
            self.write_in_database('trace_data', )
