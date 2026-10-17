from dataclasses import dataclass

from cyclonedds.idl import IdlStruct
from cyclonedds.idl.types import int64, uint32


@dataclass
class VehicleState(IdlStruct):
    header_id: uint32
    timestamp: str
    version: str
    manufacturer: str
    serial_number: str
    payload_json: str
    t_send_ns: int64
