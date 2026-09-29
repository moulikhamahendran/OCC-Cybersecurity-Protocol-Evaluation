#!/usr/bin/env python3
from dataclasses import dataclass
import json
from pathlib import Path
import time
import uuid
DATASET_SCHEMA_VERSION="1.0"; PAYLOAD_SCHEMA_VERSION="0.1"
TELEMETRY_TOPIC="fair_v1_vm001_telemetry"; ECHO_TOPIC="fair_v1_vm001_echo"
def now_us(): return time.monotonic_ns()//1000
@dataclass
class Telemetry:
    schema_ver:str; serialNumber:str; seq:int; t_sched_us:int; speed:float; pos_x:float; pos_y:float; heading:float; battery_pct:float; state:str
@dataclass
class Echo:
    serialNumber:str; seq:int
class EventLogger:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.file=self.path.open("x",encoding="utf-8",buffering=1)
    def write(self,event): self.file.write(json.dumps(event,separators=(",",":"),sort_keys=True)+"\n"); self.file.flush()
    def close(self): self.file.close()
class FairDdsOccCore:
    def __init__(self,*,run_id,clock_domain,service_id,event_logger): self.run_id=run_id; self.clock_domain=clock_domain; self.service_id=service_id; self.event_logger=event_logger
    def _event(self,t,event_type,event_time_us):
        return {"event_id":str(uuid.uuid4()),"run_id":self.run_id,"serialNumber":t.serialNumber,"seq":t.seq,"protocol":"dds","event_type":event_type,"event_time_us":event_time_us,"clock_domain":self.clock_domain,"service_id":self.service_id,"protocol_correlation":{"telemetry_topic":TELEMETRY_TOPIC,"echo_topic":ECHO_TOPIC,"dds_reliability":"RELIABLE"},"dataset_schema_version":DATASET_SCHEMA_VERSION,"event_source_layer":"fair_echo_application"}
    def process(self,t,writer,*,t_occ_rx_us):
        if t.schema_ver!=PAYLOAD_SCHEMA_VERSION: raise ValueError("schema_ver mismatch")
        if not t.serialNumber or t.seq<0 or t.seq>599: raise ValueError("correlation fields invalid")
        self.event_logger.write(self._event(t,"occ_rx",t_occ_rx_us))
        echo=Echo(t.serialNumber,t.seq)
        t_occ_tx_us=now_us()
        writer.write(echo)
        self.event_logger.write(self._event(t,"occ_tx",t_occ_tx_us))
        return echo
