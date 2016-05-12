# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright 2015-2016 by EcpyHqcLegacy Authors, see AUTHORS for more details.
#
# Distributed under the terms of the BSD license.
#
# The full license is in the file LICENCE, distributed with this software.
# -----------------------------------------------------------------------------
"""Compatibility package providing HQCMeas tasks and drivers in Ecpy.

"""
from __future__ import (division, unicode_literals, print_function,
                        absolute_import)

import enaml


def list_manifests():
    """List the manifest that should be regsitered when the main Ecpy app is
    started.

    """
    with enaml.imports():
        from .manifest import HqcLegacyManifest
    return [HqcLegacyManifest]
