"""
data/reference.py — Static product catalogue and fault taxonomy
"""

DAILY_LITRES     = 20_000 * 24   # 480,000 L/day at 20,000 L/hr
PET_BOTTLES_CASE = 12
CAN_BOTTLES_CASE = 24

LINES  = list(range(1, 9))
SHIFTS = [
    "Morning (06:00–14:00)",
    "Afternoon (14:00–22:00)",
    "Night (22:00–06:00)",
]

# ── Product catalogue ─────────────────────────────────────────────────────────
PRODUCTS = {
    '1': {
        'productName': 'Bigi',
        'flavors': [
            'Cola', 'Orange', 'Lemon-Lime', 'Tropical', 'Apple', 'Chapman',
            'Soda', 'Zero Cola', 'Bitter Lemon', 'Ginger Ale', 'Ginger Lemon',
            'Tamarind', 'Cherry Cola',
        ],
        'packSizes':  ['35cl', '50cl', '60cl'],
        'packagings': ['PET'],
    },
    '2': {
        'productName': 'Fearless',
        'flavors': ['Classic', 'Red Berry'],
        'packSizes':  ['33cl', '35cl', '50cl'],
        'packagings': ['PET', 'CAN'],
    },
    '3': {
        'productName': 'Sosa Juice',
        'flavors': ['Orange', 'Apple', 'Mixed Berries', 'Cranberry', 'Orange-Mango'],
        'packSizes':  ['35cl', '1L'],
        'packagings': ['PET'],
    },
    '4': {
        'productName': 'Premium Water',
        'flavors': ['Natural'],
        'packSizes':  ['60cl', '75cl', '1.5L'],
        'packagings': ['PET'],
    },
}

PRODUCT_NAMES      = [p['productName'] for p in PRODUCTS.values()]
PRODUCT_NAME_TO_ID = {p['productName']: pid for pid, p in PRODUCTS.items()}


# ── Target computation ────────────────────────────────────────────────────────
def _daily_cases(pack_size_str: str, packaging: str) -> int:
    s = pack_size_str.strip()
    litres = float(s.replace("cl", "")) / 100 if s.endswith("cl") else float(s.replace("L", ""))
    per_case = CAN_BOTTLES_CASE if packaging == "CAN" else PET_BOTTLES_CASE
    return round((DAILY_LITRES / litres) / per_case)


# Pre-computed lookup: PRODUCT_TARGETS[product_name][pack_size][packaging] = int
PRODUCT_TARGETS: dict[str, dict[str, dict[str, int]]] = {}
for _pid, _pd in PRODUCTS.items():
    _name = _pd['productName']
    PRODUCT_TARGETS[_name] = {}
    for _size in _pd['packSizes']:
        PRODUCT_TARGETS[_name][_size] = {}
        for _pkg in _pd['packagings']:
            PRODUCT_TARGETS[_name][_size][_pkg] = _daily_cases(_size, _pkg)


def get_target(product_name: str, pack_size: str, packaging: str) -> int:
    try:
        return PRODUCT_TARGETS[product_name][pack_size][packaging]
    except KeyError:
        return 0


# ── Fault taxonomy ────────────────────────────────────────────────────────────
FAULT_DATA = {
    'Mixer':                ['leaking', 'co2 valve calibration'],
    'Filler':               ['high torque capper head', 'drive block', 'cap intermediate conv malf',
                             'lifting unit faulty', 'activation EOP Error', 'cleaning', 'base cooling',
                             'bad capping', 'cap elevator', 'bad transfer',
                             'underfill/filling valve/lifting cylinder'],
    'Blow Mould':           ['several preforms not fitted', 'speed reduction', 'workloose spring',
                             'circuit breaker', 'blowing nozzle', 'lifting cylinder', 'faulty sensor',
                             'mould station', 'intermediate conv', 'dented bottle',
                             'sliding rail misalignment/preform hook', 'isolation station',
                             'air conditioning', 'preform gap', 'cooling shield',
                             'drive block/clamps misalignment'],
    'Labeler':              ['VGC malfunctioned', 'cutting deviation',
                             'adjustment of discharge conveyor guide', 'circuit breaker',
                             'glue splash', 'cleaning', 'bottle fall at discharge',
                             'vacuum generator pump'],
    'Variopac':             ['pack conv sensor malf', 'compensating belt', 'bottle fall',
                             'transfer belt', 'bad pack', 'pusher bar'],
    'Palletizer':           ['conveyor jerk', 'gripper malf', 'circuit breaker',
                             'pack move to spacing conv', 'layerpad inserter malf',
                             'servo inverter', 'safety malf', 'pusher bar', 'layerpad picker malf'],
    'Conveyor':             ['bottle fall accumulation', 'malf', 'pack conv malf',
                             'back up sensor malf', 'glideliner'],
    'Checkmat':             ['checkmat'],
    'Preforms':             ['defect'],
    'Insufficient Preform': ['insufficient preform'],
    'Cap':                  ['cap hook'],
    'Utility':              ['low air pressure', 'cooling water too high'],
    'WH':                   ['space constraint', 'forklift delay'],
    'Power':                ['downtime'],
    'Coding Machine':       ['not working'],
    'CO2':                  ['CO2 pressure low'],
    'KKT':                  ['cooling interrupted'],
    'Blow Mould Overhaul':  ['on hold due to particles'],
}

FAULT_MACHINES = list(FAULT_DATA.keys())