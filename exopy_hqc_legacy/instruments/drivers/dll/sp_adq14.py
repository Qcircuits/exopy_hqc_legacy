# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright 2015-2018 by ExopyHqcLegacy Authors, see AUTHORS for more details.
#
# Distributed under the terms of the BSD license.
#
# The full license is in the file LICENCE, distributed with this software.
# -----------------------------------------------------------------------------
"""Driver for the ADQ14 digitizer card.

"""
import os
import time
import atexit
import ctypes
import numpy as np

from pyclibrary import CLibrary

from ..dll_tools import DllInstrument


class ADQControlUnit(object):
    """Control unit for the ADQ devices.

    """

    _instance = None

    def __new__(cls, library):
        if cls._instance is not None:
            return cls._instance

        self = super(ADQControlUnit, cls).__new__(cls)
        self.library = library
        self.id = library.CreateADQControlUnit()()
        self._boards = []
        atexit.register(self._cleanup)
        cls._instance = self
        return self

    def list_boards(self):
        """List the detected boards.

        """
        res = self.library.ControlUnit_ListDevices(self.id)
        assert res()
        arr = [res[1][i] for i in range(res[2])]
        return arr

    def setup_board(self, board_id):
        """Prepare a board for communication and return its index.

        """
        if board_id not in self._boards:
            assert self.library.ControlUnit_OpenDeviceInterface(self.id,
                                                                board_id)()
            assert self.library.ControlUnit_SetupDevice(self.id,
                                                        board_id)()
            self._boards.append(board_id)
        return self._boards.index(board_id) + 1

    def destroy_board(self, b_id):
        """Destroy the specified board.

        """
        self.library.ControlUnit_DeleteADQ(self.id, b_id)
        del self._boards[b_id-1]

    def enable_logging(self, level, path):
        """
        """
        self.library.ControlUnit_EnableErrorTrace(self.id, level, path)

    def _cleanup(self):
        """Make sure we disconnect all the boards and destroy the unit.

        """
        for i, b_id in enumerate(self._boards):
            self.library.ControlUnit_DeleteADQ(self.id, i)

        self.library.DeleteADQControlUnit(self.id)


class SPADQ14(DllInstrument):
    """Driver for the SP Devices ADQ 14 card 2 channel AC coupled.

    """

    def __init__(self, connection_info, caching_allowed=True,
                 caching_permissions={}, auto_open=True):

        super(SPADQ14, self).__init__(connection_info, caching_allowed,
                                      caching_permissions, auto_open)
        self._infos = connection_info
        self._setup_library()
        self._id = None

        if auto_open:
            self.open_connection()

    def open_connection(self):
        """Setup the right card based on the vendor id.

        """
        cu = ADQControlUnit(self._dll)
        cu.enable_logging(3, b"C:\\Logs")
        boards = cu.list_boards()
        board_id = None
        for i, b in enumerate(boards):
            if b.ProductID == self._dll.PID_ADQ14:
                # Setup the communication.
                # Far from ideal but I do not know how to link serail number
                # and Vendor ID, should ask !
                b_id = cu.setup_board(i)
                serial = self._dll.GetBoardSerialNumber(cu.id, b_id)()
                if serial.decode('ascii') == self._infos['instr_id']:
                    board_id = b_id
                    break

        if board_id is None:
            raise ValueError('No ADQ14 with id %s' % self._infos['instr_id'])

        assert self._dll.IsStartedOK(cu.id, board_id)()
        self._cu_id = cu.id
        self._id = board_id

    def close_connection(self):
        """Do not explicitly close the board as it may re-arrange the boards
        indexes.

        """
        cu = ADQControlUnit(self._dll)
        cu.destroy_board(self._id)

    def configure_board(self):
        """Set the usual settings for the card.

        """
        # Use the internal clock with an external 10MHz reference.
        self._dll.SetClockSource(self._cu_id, self._id,
                                 self._dll.ADQ_CLOCK_INT_EXTREF)

        # Set trigger to external source.
        self._dll.SetTriggerMode(self._cu_id, self._id,
                                 self._dll.ADQ_EXT_TRIGGER_MODE)

        # Set external trigger to triger on rising edge.
        self._dll.SetTriggerEdge(self._cu_id, self._id, 2, 1)

    def get_traces(self, channels, duration, delay, records_per_capture,
                   retry=1, average=False):
        """Acquire the average signal on both channels.

        Parameters
        ----------
        channels : tuple
            Tuple of boolean indicating which channels are active.

        duration : float
            Time during which to acquire the data (in seconds)

        delay : float
            Time to wait after a trigger before starting next measure
            (in seconds).

        records_per_capture : int
            Number of records to acquire (per channel)

        retry : int, optional
            Number of time to retry acquisition if data recuperation fails.

        average : bool, optional
            Should traces be averaged.

        Returns
        -------
        data : list
            List containing the acquired data per channel, average or not based
            on the average parameter.

        """
        # Set trigger delay
        n = int(round(delay/2e-9))
        assert 0 <= n < 62, 'Delay must be at most 61 cycles (%d)' % n
        assert self._dll.SetTriggerHoldOffSamples(self._cu_id, self._id, n)()

        # Number of samples per record.
        samples_per_sec = 500e6
        samples_per_record = int(round(samples_per_sec*duration))

        mask = (0x01 if channels[0] else 0) + (0x02 if channels[1] else 0)
        assert self._dll.MultiRecordSetChannelMask(self._cu_id, self._id, mask)
        assert self._dll.MultiRecordSetup(self._cu_id, self._id,
                                          records_per_capture,
                                          samples_per_record)()

        # Alloc memory for both channels (using numpy arrays)
        buffer_size = samples_per_record*records_per_capture
        buffers = []
        avg = []
        for c in channels:
            buf = (np.ascontiguousarray(np.empty(buffer_size, dtype=np.int16))
                   if c else np.zeros(1, dtype=np.uint16))
            buffers.append(buf)
            avg.append(np.zeros(samples_per_record) if c else np.zeros(1))

        chs = tuple([i for i, c in enumerate(channels) if c])
        buffers_ptr = (ctypes.c_void_p*2)(*(b.ctypes.data_as(ctypes.c_void_p)
                                            for b in buffers))

        cu = self._cu_id
        id_ = self._id
        bytes_per_sample = self._dll.GetNofBytesPerSample(cu, id_)[2]

        assert self._dll.DisarmTrigger(self._cu_id, self._id)()
        while not self._dll.ArmTrigger(self._cu_id, self._id)():
            time.sleep(0.0001)

        # Wait for all records to be acquired.
        acq_records = self._dll.GetAcquiredRecords.func
        get_data = self._dll.GetData.func
        retrieved_records = 0
        while retrieved_records < records_per_capture:
            # Wait for a record to be acquired.
            n_records = (acq_records(cu, id_) - retrieved_records)

            # If we are not averaging we wait for all records to be acquired.
            if not n_records or (not average and
                                 n_records < records_per_capture):
                time.sleep(1e-6)
                continue
            if not get_data(cu, id_, buffers_ptr,
                            n_records*samples_per_record,
                            bytes_per_sample,
                            retrieved_records,
                            n_records,
                            mask,
                            0,
                            samples_per_record,
                            0x00):
                del avg, buffers
                self._dll.DisarmTrigger(self._cu_id, self._id)
                self._dll.MultiRecordClose(self._cu_id, self._id)
                self.close_connection()
                self._setup_library()
                self.open_connection()
                self.configure_board()
                if retry:
                    return self.get_traces(channels, duration, delay,
                                           records_per_capture, retry-1, average)
                else:
                    msg = 'Failed to retrieve data from ADQ14'
                    raise RuntimeError(msg)

            if average:
                for c in chs:
                    avg[c] += np.sum(
                        np.reshape(buffers[c],
                                   (-1, samples_per_record))[:n_records], 0)

            retrieved_records += n_records

        if average:
            for c in chs:
                avg[c] /= records_per_capture

        self._dll.DisarmTrigger(self._cu_id, self._id)
        self._dll.MultiRecordClose(self._cu_id, self._id)

        # Get the offset in volt for each channel is ignored.
        # The range is 1.9 Vpp according to the data sheet 2**16 = 65536
        if average:
            for c in chs:
                avg[c] *= 1.9/65535
        else:
            for i, c in enumerate(channels):
                if c:
                    buffers[i] = np.reshape(buffers[i].astype(np.float32),
                                  (-1, samples_per_record)) * 1.9/65535

        return avg if average else buffers

    def _setup_library(self):
        """Load and initialize the dll.

        """
        cache_path = str(os.path.join(os.path.dirname(__file__),
                                      'adq14.pycctypes.libc'))
        library_dir = os.path.join(self._infos.get('lib_dir', ''),
                                   'ADQAPI.dll')
        header_dir = os.path.join(self._infos.get('header_dir', ''),
                                  'ADQAPI.h')

        self._dll = CLibrary(library_dir, [header_dir], cache=cache_path,
                             prefix=['ADQ',  'ADQ_'], convention='cdll')
