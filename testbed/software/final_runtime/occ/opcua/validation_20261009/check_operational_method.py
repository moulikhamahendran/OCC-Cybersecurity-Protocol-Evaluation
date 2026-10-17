import asyncio, importlib.util, json, tempfile
from pathlib import Path
from asyncua import Server, Client, ua
R=Path(__file__).resolve().parents[5]
spec=importlib.util.spec_from_file_location('operational', R/'testbed/final_runtime/occ/opcua/opcua_operational_server.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
async def run():
 with tempfile.TemporaryDirectory() as tmp:
  logger=m.EventLogger(Path(tmp)/'events.jsonl')
  service=m.FairOpcuaService(run_id='software-only',clock_domain='local',service_id='test',event_logger=logger)
  server=Server(); await server.init(); server.set_endpoint('opc.tcp://127.0.0.1:14840/occ-test/'); server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
  idx,obj,method=await m.add_fair_method(server,service)
  async with server:
   async with Client('opc.tcp://127.0.0.1:14840/occ-test/') as client:
    ci=await client.get_namespace_index(m.NAMESPACE_URI)
    node=client.get_node(ua.NodeId(m.OBJECT_NODEID,ci))
    for seq in (599,600,3400000,3400001,4294967295):
     args=[ua.Variant('runtime-1.0',ua.VariantType.String),ua.Variant('VM-001',ua.VariantType.String),ua.Variant(seq,ua.VariantType.UInt32),ua.Variant(123456789012,ua.VariantType.Int64)]
     args += [ua.Variant(v,ua.VariantType.Float) for v in (1.25,2.5,3.75,90.0,82.5)]
     args += [ua.Variant('RUNNING',ua.VariantType.String)]
     result=await node.call_method(ua.NodeId(m.METHOD_NODEID,ci),*args)
     assert list(result)==['VM-001',seq],result
  logger.close(); rows=[json.loads(s) for s in (Path(tmp)/'events.jsonl').read_text().splitlines()]
  assert len(rows)==10
  for i,seq in enumerate((599,600,3400000,3400001,4294967295)):
   assert [x['event_type'] for x in rows[2*i:2*i+2]]==['occ_rx','occ_tx']
   assert all(x['seq']==seq and x['serialNumber']=='VM-001' for x in rows[2*i:2*i+2])
  print('PASS: local OPC UA method calls, full UInt32 sequence, correlated acknowledgments, and paired receive/transmit events. SOFTWARE ONLY; no ESP32 evidence.')
asyncio.run(run())
