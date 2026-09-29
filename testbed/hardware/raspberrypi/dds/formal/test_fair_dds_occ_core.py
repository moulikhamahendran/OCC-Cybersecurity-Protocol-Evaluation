#!/usr/bin/env python3
import json,tempfile
from pathlib import Path
from jsonschema import Draft202012Validator
import fair_dds_occ_core as app
class W:
    def __init__(self): self.samples=[]
    def write(self,x): self.samples.append(x)
def main():
    here=Path(__file__).resolve().parent; repo=here
    while repo!=repo.parent and not (repo/"testbed/docs/fair_v1/schemas").exists(): repo=repo.parent
    schema=json.loads((repo/"testbed/docs/fair_v1/schemas/fair_v1_occ_message_event.schema.json").read_text()); Draft202012Validator.check_schema(schema)
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/"events.jsonl"; log=app.EventLogger(path); core=app.FairDdsOccCore(run_id="TEST-DDS-001",clock_domain="test_monotonic",service_id="fair-dds-occ",event_logger=log); w=W(); old=app.now_us; app.now_us=lambda:1000200
        try: e=core.process(app.Telemetry("0.1","VM-001",123,12300000,1.0,2.0,3.0,4.0,80.0,"RUNNING"),w,t_occ_rx_us=1000000)
        finally: app.now_us=old
        log.close(); assert e.serialNumber=="VM-001" and e.seq==123 and len(w.samples)==1
        events=[json.loads(x) for x in path.read_text().splitlines()]; assert len(events)==2
        for ev in events: Draft202012Validator(schema).validate(ev)
        assert events[0]["event_type"]=="occ_rx" and events[0]["event_time_us"]==1000000
        assert events[1]["event_type"]=="occ_tx" and events[1]["event_time_us"]==1000200
    print("FAIR_V1_PI_DDS_OCC_CORE_TEST: PASS"); print("OCC_EVENT_SCHEMA_VALIDATION: PASS")
if __name__=="__main__": main()
