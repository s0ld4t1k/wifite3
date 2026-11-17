#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OUI manufacturer database loading logic."""

import re

from ..util.paths import find_data_file


def load_manufacturers(cls):
    """Lazy-load OUI manufacturer database on first access."""
    if cls._manufacturers_loaded:
        return
    cls._manufacturers_loaded = True
    mfr_file = find_data_file('ieee-oui.txt')
    if mfr_file is None:
        return
    cls.manufacturers = {}
    with open(mfr_file, encoding='utf-8', errors='replace') as f:
        for line in f:
            if not re.match(r'^\w', line):
                continue
            line = line.replace('(hex)', '').replace('(base 16)', '')
            fields = line.split()
            if len(fields) >= 2:
                cls.manufacturers[fields[0]] = ' '.join(fields[1:]).rstrip('.')
