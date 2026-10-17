from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[5]
c=(r/'testbed/hardware/esp32/opcua/formal/fair_opcua_common/fair_opcua_transport.c').read_text()
expr=c[c.index('!(transport->operational_telemetry'):c.index('\n    ) {',c.index('!(transport->operational_telemetry'))]
s='''#include <assert.h>
#include <string.h>
#include "fair_v1_core.h"
typedef struct { bool operational_telemetry; } transport_t;
static bool rejected(transport_t *transport, fair_v1_payload_t *payload, fair_v1_slot_t *slot) { return EXPR; }
int main(void) {
 transport_t t={false}; fair_v1_slot_t s={0}; fair_v1_payload_t p={.schema_ver="0.1",.serialNumber="VM-001",.state="RUNNING"};
 assert(fair_v1_slot_init(&s,599,123)); p.seq=599; p.t_sched_us=123; assert(!rejected(&t,&p,&s));
 p.seq=s.seq=600; assert(rejected(&t,&p,&s));
 t.operational_telemetry=true; p.schema_ver="runtime-1.0";
 unsigned seqs[]={600,3400000,3400001,4294967295U};
 for(unsigned i=0;i<4;i++){p.seq=s.seq=seqs[i];assert(!rejected(&t,&p,&s));}
 p.seq--; assert(rejected(&t,&p,&s)); p.seq=s.seq;
 p.t_sched_us++;assert(rejected(&t,&p,&s));p.t_sched_us=s.t_sched_us;
 p.schema_ver="0.1";assert(rejected(&t,&p,&s));p.schema_ver="runtime-1.0";
 p.serialNumber="";assert(rejected(&t,&p,&s));
 assert(!fair_v1_slot_init(&s,3400000,123));
 return 0;
}
'''.replace('EXPR',expr)
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'check.c').write_text(s)
 subprocess.run(['cc','-Wall','-Werror','-I'+str(r/'testbed/hardware/esp32/fair_v1_core/include'),str(p/'check.c'),str(r/'testbed/hardware/esp32/fair_v1_core/fair_v1_core.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
print('PASS: actual submit validation predicate accepts high operational sequences, rejects mismatched sequence/timestamp/schema/identity, and preserves formal 599/600 boundary.')
