"""
data/reference.py — Static product catalogue and fault taxonomy
"""

HOURLY_LITRES    = 20_000        # 20,000 L/hr ideal throughput
DAILY_LITRES     = HOURLY_LITRES * 24   # 480,000 L/day
PET_BOTTLES_CASE = 12
CAN_BOTTLES_CASE = 24

LINES  = list(range(1, 9))
SHIFTS = [
    "Morning (07:00–14:00)",
    "Afternoon (14:00–21:00)",
    "Night (21:00–07:00)",
]

# Shift hours for time calculations
SHIFT_HOURS = {
    "Morning":   7,
    "Afternoon": 7,
    "Night":    10,
}

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
def _cases_per_hour(pack_size_str: str, packaging: str) -> float:
    s = pack_size_str.strip()
    litres = float(s.replace("cl", "")) / 100 if s.endswith("cl") else float(s.replace("L", ""))
    per_case = CAN_BOTTLES_CASE if packaging == "CAN" else PET_BOTTLES_CASE
    return (HOURLY_LITRES / litres) / per_case


# Pre-computed lookups keyed by [product_name][pack_size][packaging]
PRODUCT_TARGETS: dict[str, dict[str, dict[str, int]]]   = {}  # daily baseline
HOURLY_TARGETS:  dict[str, dict[str, dict[str, float]]] = {}  # cases/hr

for _pid, _pd in PRODUCTS.items():
    _pname = _pd['productName']
    PRODUCT_TARGETS[_pname] = {}
    HOURLY_TARGETS[_pname]  = {}
    for _size in _pd['packSizes']:
        PRODUCT_TARGETS[_pname][_size] = {}
        HOURLY_TARGETS[_pname][_size]  = {}
        for _pkg in _pd['packagings']:
            _cph = _cases_per_hour(_size, _pkg)
            HOURLY_TARGETS[_pname][_size][_pkg]  = _cph
            PRODUCT_TARGETS[_pname][_size][_pkg] = round(_cph * 24)


def get_target(product_name: str, pack_size: str, packaging: str) -> int:
    """Daily baseline target (cases). Used as opening estimate."""
    try:
        return PRODUCT_TARGETS[product_name][pack_size][packaging]
    except KeyError:
        return 0


def get_run_target(product_name: str, pack_size: str, packaging: str,
                   actual_hours: float) -> int:
    """Target cases for a run of the given duration (hourly rate × hours)."""
    try:
        cph = HOURLY_TARGETS[product_name][pack_size][packaging]
        return max(1, round(cph * actual_hours))
    except KeyError:
        return 0


# ── Fault taxonomy ────────────────────────────────────────────────────────────
FAULT_DATA = {
    'Blow Mould': [
        'Preform jammed- roller orientor/ Sorter',
        'Preform hook at oven infeed',
        'Cooling interrupted/KKT chiller malfunction',
        'Preform jam at sliding rail/elevator',
        'Preform tipper/hopper malfunctioned',
        'Base Cooling Malfunctioned',
        'Heating Controller Machine Malfunctioned',
        'Compressed Air Supply System component Malfunctioned',
        'Replacement of Preblowing Valve in Station',
        'Lubrication of heating Mandrel',
        'Replacement of damaged water connector hose at station',
        'Broken Heating Mandrel Actuate Mandrel Monitoring Device',
        'Bottle Jam at Mould station - Engr. Intervention',
        'Intervention on Bottle Drop at Discharge Starwheel',
        'Removal of Dirt',
        'Clutch misaligned due to drive block (Realignment)',
        'Servo inverter signal malfunction (Mould)',
        'Misaligned Clamp',
        'Adjustment of Parameters due to ring bottle',
        'Stretching Motor Temperature Too High'
    ],
    'Filler': [
        'Cap Sorter Malfunctioned',
        'Station Pilot Valve ShortCircuit - Automation Intervention',
        'Bad transfer- Several drive block due to/bad shaft side/transfer worm/intermediate starwheel',
        'Troubleshooting the cause of frequent cap hook on rail',
        'Cap Rail vibrator malfunctioned due to cut air hose',
        'Underfill - Filling station malfunctioned',
        'Base cooling system failed/pump malfunctioned',
        'Cooling Interrupted',
        'Replacement of Seal (DN 80) at product pipe',
        'Product level probe sensor malfunctioned',
        'Drive Block at carousel Discharge/transfer starwheels',
        'Level Transmitter sensor (LT100) malfunctioned',
        'Misaligned sensor - lack of caps',
        'Container monitoring device tripped'
    ],
    'Mixer': [
        'Replacement of Q145 valve seal',
        'Temperature too high at mixer',
        'Lack of CO2/low CO2 pressure at mixer',
        'Valve Q138 for CO2 malfunctioned',
        'Lack of Product',
        'Controller out of range (Q140) at mixer (KBQ137)'
    ],
    'Labeller': [
        'Bad splicing/Improper splicing',
        'VGC Monitoring sensor 2- no label',
        'Troubleshooting of labeller bottle fall at infeed worm',
        'Replacement of leaking vacuum hose',
        'Bottle Burst due to bad wet strip - Specialist intervention',
        'Coding Machine Tripped',
        'Adjustment of carrousel brush due to scratches',
        'Infeed worm misaligned',
        'Production sensor 2 misaligned',
        'Replacement of Centering Bell',
        'Label cut'
    ],
    'Shrink Wrapper': [
        'Wrapping bar pulled out on motion',
        'Film folding, module sensor malfunction',
        'Axis not homed at wrapping station',
        'Oven shaft seal malfunction',
        'Belt tracking sensor malfunction',
        'Collision at wrapping station',
        'Bottle fall at infeed conveyor/Jam conveyor G1114-M101',
        'Badly formed packs'
    ],
    'Palletizer': [
        'Layer length - Intervention',
        'Layer Pad Magazine Handler Malfunctioned',
        'Packs falling at loading station',
        'Gripper Belt Cut',
        'Module Conveyor Jerking',
        'Measure cycle length malfunction',
        'Automation intervention on malfunctioning shutter gripper area clear sensor',
        'Alignment of Misaligned stopping conveyor sprocket',
        'Drive signal a fault ; module1 group axis',
        'Robobox Malfunctioned at Module - Day Intervention',
        'Atlanta malfunction'
    ],
    'Conveyor': [
        'Bottles falling at glideliner',
        'Pack conveyor malfunctioned',
        'Bottles fall at flowliner',
        'Bottle fall at checkmat',
        'Bottle Fall at Glideliner',
        'Bottle falling at filler discharge conveyor',
        'Glideliner gap monitoring sensor malfunction',
        'Bottle falling at Labeller Infeed',
        'Falling bottles at labeller discharge conveyor'
    ],
    'Non-Line Machine Faults': [
        'Fine Tuning of the Line',
        'Troubleshooting Cause of CIP not flow',
        'End of production/Preparation/Start up/CIP/COP',
        'Dented/bad / wrong label supplied/Change of label/Invalid Register Mark/Out of Core',
        'Bad / no caps supply',
        'Bad / No layer pads',
        'Checkmat Malfunction/validation/Checkmat Bin Filled Up',
        'Product Sample Valve',
        'Syrup Pump - Engineer Intervention',
        'Awaiting or lack of syrup / Change of batch / Low syrup pressure',
        'Planned Maintenance',
        'Low pressure from HP compressor',
        'Low pressure from LP compressor',
        'No cooling at mixer due to utilities',
        'No / Bad pallets / Collapse / Delayed Pallet supply',
        'Power outage/UPS Change over/Maintenance',
        'Bad / no stretch film',
        'No water / Low water level/Ozone/PH issue from WTP',
        'Bad / no /wrong/ mixed preforms/not fit',
        'Anthon Paar malfunction',
        'Lack of CO2/low CO2 pressure at mixer / filler',
        'Bad shrink film/Changing of film/Film Stuck/Torn',
        'Cap Hook at chute/sorter',
        'Forklift delay',
        'Spraying Active/Capper Flushing',
        'Container Burst / Stuck in mould',
        'Utilities - Low Operating Air supply',
        'Utilities - Blowing pressure out of tolerance range',
        'Utilities - No cooling water signal at mixer',
        'WTP - No product water supplied to the line',
        'QC - Raw material testing; preform, cap, glue, film',
        'Wrong input of parameters in coding machine/ line hold/interference',
        'Bottle Fall - Bad Base/Empty Container/Adjustment of Parameter',
        'No/delay preform/cap supply',
        'Clearing of backlogs / RTF',
        'Lack of space at Warehouse (finished goods)',
        'Change of Preform/Cap Batch',
        'Stock Count',
        'CLIT/CLEANING',
        'Low brix/High brix'
    ]
}
FAULT_MACHINES = list(FAULT_DATA.keys())