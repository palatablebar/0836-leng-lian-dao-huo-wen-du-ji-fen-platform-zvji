from app.catalog import SPEC
from app.domain.calculate import calculate_rows
from app.domain.decision import decide_rows
from app.domain.prepare import prepare_rows
from app.intake.service import load

CLEAN = [{'batch_id': 'B001',
  'sensor_id': 'S01',
  'segment_start': '2026-11-20 00:00',
  'segment_end': '2026-11-20 02:00',
  'temp_c': '4.0',
  'unit': 'C',
  'probe_offset': '0'},
 {'batch_id': 'B001',
  'sensor_id': 'S01',
  'segment_start': '2026-11-20 02:00',
  'segment_end': '2026-11-20 04:00',
  'temp_c': '5.0',
  'unit': 'C',
  'probe_offset': '0'},
 {'batch_id': 'B002',
  'sensor_id': 'S02',
  'segment_start': '2026-11-20 01:00',
  'segment_end': '2026-11-20 04:00',
  'temp_c': '39.2',
  'unit': 'F',
  'probe_offset': '0.2'},
 {'batch_id': 'B002',
  'sensor_id': 'S02',
  'segment_start': '2026-11-20 04:00',
  'segment_end': '2026-11-20 05:00',
  'temp_c': '38.84',
  'unit': 'F',
  'probe_offset': '0.2'},
 {'batch_id': 'B003',
  'sensor_id': 'S03',
  'segment_start': '2026-11-20 06:00',
  'segment_end': '2026-11-20 10:00',
  'temp_c': '8.0',
  'unit': 'C',
  'probe_offset': '0'}]


def row(**changes):
    item = dict(CLEAN[0])
    item.update(changes)
    return item


def calc(rows):
    items, issues = prepare_rows(rows)
    return calculate_rows(items), issues


def run(rows):
    items, issues = prepare_rows(rows)
    return decide_rows(calculate_rows(items)), issues


def run_profile(profile):
    return run(load(profile)["rows"])
