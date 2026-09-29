#!/usr/bin/env python3
import argparse,time
from cyclonedds.domain import DomainParticipant
from cyclonedds.idl import IdlStruct
from cyclonedds.idl.types import float32,int64,uint32
from cyclonedds.listener import Listener
from cyclonedds.pub import DataWriter
from cyclonedds.qos import Policy,Qos
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from cyclonedds.util import duration
from fair_dds_occ_core import Telemetry,EventLogger,FairDdsOccCore,ECHO_TOPIC,TELEMETRY_TOPIC,now_us
class FairV1Telemetry(IdlStruct,typename="FairV1Telemetry"):
    schema_ver:str; serialNumber:str; seq:uint32; t_sched_us:int64; speed:float32; pos_x:float32; pos_y:float32; heading:float32; battery_pct:float32; state:str
class FairV1Echo(IdlStruct,typename="FairV1Echo"):
    serialNumber:str; seq:uint32
class EchoWriterAdapter:
    def __init__(self,w): self.w=w
    def write(self,e): self.w.write(FairV1Echo(serialNumber=e.serialNumber,seq=e.seq))
def convert(s): return Telemetry(s.schema_ver,s.serialNumber,int(s.seq),int(s.t_sched_us),float(s.speed),float(s.pos_x),float(s.pos_y),float(s.heading),float(s.battery_pct),s.state)
def args():
    p=argparse.ArgumentParser(); p.add_argument("--domain",type=int,default=0); p.add_argument("--run-id",required=True); p.add_argument("--clock-domain",required=True); p.add_argument("--service-id",required=True); p.add_argument("--event-log",required=True); return p.parse_args()
def main():
    a=args(); log=EventLogger(a.event_log); core=FairDdsOccCore(run_id=a.run_id,clock_domain=a.clock_domain,service_id=a.service_id,event_logger=log); dp=DomainParticipant(a.domain)
    qos=Qos(Policy.Reliability.Reliable(max_blocking_time=duration(milliseconds=100)),Policy.History.KeepLast(32),Policy.Durability.Volatile)
    tt=Topic(dp,TELEMETRY_TOPIC,FairV1Telemetry,qos=qos); et=Topic(dp,ECHO_TOPIC,FairV1Echo,qos=qos); ew=DataWriter(dp,et,qos=qos); adapter=EchoWriterAdapter(ew)
    def on_data_available(reader):
        t_occ_rx_us=now_us()
        for s in reader.take(N=32): core.process(convert(s),adapter,t_occ_rx_us=t_occ_rx_us)
    listener=Listener(on_data_available=on_data_available); reader=DataReader(dp,tt,qos=qos,listener=listener)
    print("FAIR-V1 DDS OCC application ready",flush=True)
    try:
        while True: time.sleep(1)
    finally: log.close(); del reader
if __name__=="__main__": main()
