#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "uxr/client/client.h"
#include "fair_dds_types.h"
#include "fair_dds_transport.h"

static const char *TAG="FAIR_DDS_XRCE";

static bool status_ok(uint8_t s){ return s==UXR_STATUS_OK || s==UXR_STATUS_OK_MATCHED; }

static bool secure_participant_xml(int level, char *b, size_t n)
{
    if (!b || n==0U) return false;
    const char *gov = level==FAIR_DDS_SECURITY_C1 ? "governance_c1.p7s" : "governance_c2.p7s";
    int r=snprintf(b,n,
        "<dds><participant><rtps><name>FAIR_V1_XRCE_VM001_%s</name>"
        "<propertiesPolicy><properties>"
        "<property><name>dds.sec.auth.plugin</name><value>builtin.PKI-DH</value></property>"
        "<property><name>dds.sec.auth.builtin.PKI-DH.identity_ca</name><value>file:/opt/fair-v1/dds/security/identity_ca_cert.pem</value></property>"
        "<property><name>dds.sec.auth.builtin.PKI-DH.identity_certificate</name><value>file:/opt/fair-v1/dds/security/agent_cert.pem</value></property>"
        "<property><name>dds.sec.auth.builtin.PKI-DH.private_key</name><value>file:/opt/fair-v1/dds/security/private/agent_key.pem</value></property>"
        "<property><name>dds.sec.access.plugin</name><value>builtin.Access-Permissions</value></property>"
        "<property><name>dds.sec.access.builtin.Access-Permissions.permissions_ca</name><value>file:/opt/fair-v1/dds/security/permissions_ca_cert.pem</value></property>"
        "<property><name>dds.sec.access.builtin.Access-Permissions.governance</name><value>file:/opt/fair-v1/dds/security/%s</value></property>"
        "<property><name>dds.sec.access.builtin.Access-Permissions.permissions</name><value>file:/opt/fair-v1/dds/security/permissions_agent.p7s</value></property>"
        "<property><name>dds.sec.crypto.plugin</name><value>builtin.AES-GCM-GMAC</value></property>"
        "</properties></propertiesPolicy></rtps></participant></dds>",
        level==FAIR_DDS_SECURITY_C1 ? "C1" : "C2", gov);
    return r>0 && (size_t)r<n;
}

static void on_topic(uxrSession *session, uxrObjectId object_id, uint16_t request_id, uxrStreamId stream_id, ucdrBuffer *ub, uint16_t length, void *args)
{
    const int64_t t_ack_rx_us=esp_timer_get_time();
    (void)session; (void)request_id; (void)stream_id; (void)length;
    fair_dds_transport_t *t=(fair_dds_transport_t*)args;
    if (!t || !ub) return;
    if (object_id.id!=t->echo_reader_id.id || object_id.type!=t->echo_reader_id.type) return;
    char serial[64]={0};
    fair_dds_echo_rx_t echo={.serialNumber=serial,.serialNumber_capacity=sizeof(serial),.seq=0U};
    if (!fair_dds_deserialize_echo(ub,&echo)){ ESP_LOGW(TAG,"echo decode failed"); return; }
    if (strcmp(echo.serialNumber,t->serial_number)!=0){ ESP_LOGW(TAG,"echo serial mismatch"); return; }
    if (t->echo_callback) t->echo_callback(t->echo_callback_context,echo.seq,t_ack_rx_us);
}

static bool create_entities(fair_dds_transport_t *t)
{
    uxrObjectId participant=uxr_object_id(1,UXR_PARTICIPANT_ID);
    uxrObjectId telemetry_topic=uxr_object_id(1,UXR_TOPIC_ID);
    uxrObjectId echo_topic=uxr_object_id(2,UXR_TOPIC_ID);
    uxrObjectId publisher=uxr_object_id(1,UXR_PUBLISHER_ID);
    uxrObjectId subscriber=uxr_object_id(1,UXR_SUBSCRIBER_ID);
    t->telemetry_writer_id=uxr_object_id(1,UXR_DATAWRITER_ID);
    t->echo_reader_id=uxr_object_id(1,UXR_DATAREADER_ID);
    uint16_t req[7]={0};
    static char xml[4096];
    if (t->security_level==FAIR_DDS_SECURITY_C0){
        req[0]=uxr_buffer_create_participant_bin(&t->session,t->reliable_out,participant,0U,"FAIR_V1_XRCE_VM001_C0",UXR_REPLACE);
    } else {
        if (!secure_participant_xml(t->security_level,xml,sizeof(xml))) return false;
        req[0]=uxr_buffer_create_participant_xml(&t->session,t->reliable_out,participant,0U,xml,UXR_REPLACE);
    }
    req[1]=uxr_buffer_create_topic_bin(&t->session,t->reliable_out,telemetry_topic,participant,FAIR_DDS_TELEMETRY_TOPIC,FAIR_DDS_TELEMETRY_TYPE,UXR_REPLACE);
    req[2]=uxr_buffer_create_topic_bin(&t->session,t->reliable_out,echo_topic,participant,FAIR_DDS_ECHO_TOPIC,FAIR_DDS_ECHO_TYPE,UXR_REPLACE);
    req[3]=uxr_buffer_create_publisher_bin(&t->session,t->reliable_out,publisher,participant,UXR_REPLACE);
    req[4]=uxr_buffer_create_subscriber_bin(&t->session,t->reliable_out,subscriber,participant,UXR_REPLACE);
    uxrQoS_t qos={.durability=UXR_DURABILITY_VOLATILE,.reliability=UXR_RELIABILITY_RELIABLE,.history=UXR_HISTORY_KEEP_LAST,.depth=32U};
    req[5]=uxr_buffer_create_datawriter_bin(&t->session,t->reliable_out,t->telemetry_writer_id,publisher,telemetry_topic,qos,UXR_REPLACE);
    req[6]=uxr_buffer_create_datareader_bin(&t->session,t->reliable_out,t->echo_reader_id,subscriber,echo_topic,qos,UXR_REPLACE);
    uint8_t status[7]={0};
    if (!uxr_run_session_until_all_status(&t->session,3000,req,status,7U)) return false;
    for (size_t i=0;i<7U;++i) if (!status_ok(status[i])){ ESP_LOGE(TAG,"entity status[%u]=%u",(unsigned)i,(unsigned)status[i]); return false; }
    uxrDeliveryControl dc={0};
    dc.max_samples=UXR_MAX_SAMPLES_UNLIMITED;
    (void)uxr_buffer_request_data(&t->session,t->reliable_out,t->echo_reader_id,t->reliable_in,&dc);
    uxr_flash_output_streams(&t->session);
    return true;
}

static bool open_session(fair_dds_transport_t *t)
{
    if (!uxr_init_udp_transport(&t->udp_transport,UXR_IPv4,t->agent_ip,t->agent_port)) return false;
    t->udp_initialized=true;
    uxr_init_session(&t->session,&t->udp_transport.comm,0xAAAABBBB);
    if (!uxr_create_session(&t->session)){ uxr_close_udp_transport(&t->udp_transport); t->udp_initialized=false; return false; }
    t->session_created=true;
    t->reliable_out=uxr_create_output_reliable_stream(&t->session,t->reliable_out_buffer,sizeof(t->reliable_out_buffer),FAIR_DDS_XRCE_STREAM_HISTORY);
    t->reliable_in=uxr_create_input_reliable_stream(&t->session,t->reliable_in_buffer,sizeof(t->reliable_in_buffer),FAIR_DDS_XRCE_STREAM_HISTORY);
    uxr_set_topic_callback(&t->session,on_topic,t);
    if (!create_entities(t)){ (void)uxr_delete_session(&t->session); t->session_created=false; uxr_close_udp_transport(&t->udp_transport); t->udp_initialized=false; return false; }
    t->entities_ready=true;
    return true;
}

static void close_session(fair_dds_transport_t *t)
{
    if (t->session_created){ (void)uxr_delete_session(&t->session); t->session_created=false; }
    t->entities_ready=false;
    if (t->udp_initialized){ uxr_close_udp_transport(&t->udp_transport); t->udp_initialized=false; }
}

static void session_task(void *arg)
{
    fair_dds_transport_t *t=(fair_dds_transport_t*)arg;
    while (t && t->session_task_run){
        if (t->session_mutex && xSemaphoreTake(t->session_mutex,pdMS_TO_TICKS(10))==pdTRUE){
            if (t->session_created) (void)uxr_run_session_timeout(&t->session,1);
            xSemaphoreGive(t->session_mutex);
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    if (t) t->session_task=NULL;
    vTaskDelete(NULL);
}

bool fair_dds_transport_init(fair_dds_transport_t *t,const char *ip,const char *port,const char *serial,int security_level)
{
    if (!t||!ip||!port||!serial||!ip[0]||!port[0]||!serial[0]||security_level<0||security_level>2) return false;
    memset(t,0,sizeof(*t));
    if (snprintf(t->agent_ip,sizeof(t->agent_ip),"%s",ip)<=0) return false;
    if (snprintf(t->agent_port,sizeof(t->agent_port),"%s",port)<=0) return false;
    if (snprintf(t->serial_number,sizeof(t->serial_number),"%s",serial)<=0) return false;
    t->security_level=security_level;
    t->session_mutex=xSemaphoreCreateMutex();
    return t->session_mutex!=NULL;
}

bool fair_dds_transport_start(fair_dds_transport_t *t)
{
    if (!t||!t->session_mutex) return false;
    if (xSemaphoreTake(t->session_mutex,pdMS_TO_TICKS(1000))!=pdTRUE) return false;
    bool ok=open_session(t);
    xSemaphoreGive(t->session_mutex);
    if (!ok) return false;
    t->session_task_run=true;
    if (xTaskCreate(session_task,"fair_dds_xrce",6144,t,5,&t->session_task)!=pdPASS){ t->session_task_run=false; return false; }
    return true;
}

bool fair_dds_transport_ready(fair_dds_transport_t *t){ return t && t->session_created && t->entities_ready; }

bool fair_dds_transport_reconnect(fair_dds_transport_t *t)
{
    if (!t||!t->session_mutex) return false;
    if (xSemaphoreTake(t->session_mutex,pdMS_TO_TICKS(3000))!=pdTRUE) return false;
    close_session(t);
    bool ok=open_session(t);
    xSemaphoreGive(t->session_mutex);
    return ok;
}

int fair_dds_transport_set_echo_callback(fair_dds_transport_t *t,fair_dds_echo_callback_t cb,void *ctx)
{
    if (!t) return -1;
    t->echo_callback=cb; t->echo_callback_context=ctx; return 0;
}

int fair_dds_transport_enqueue_slot(fair_dds_transport_t *t,fair_v1_slot_t *slot,const char *data,int len)
{
    if (!t||!slot||!data||len<=0||!t->session_mutex) return -1;
    if (xSemaphoreTake(t->session_mutex,pdMS_TO_TICKS(20))!=pdTRUE){
        int64_t ts=esp_timer_get_time(); (void)fair_v1_slot_mark_send_result(slot,ts,false); return FAIR_DDS_ENQUEUE_ERR_MUTEX_TIMEOUT;
    }
    if (!t->session_created||!t->entities_ready){
        int64_t ts=esp_timer_get_time(); (void)fair_v1_slot_mark_send_result(slot,ts,false); xSemaphoreGive(t->session_mutex); return -2;
    }
    const int64_t t_send_us=esp_timer_get_time();
    const bool queued=uxr_buffer_topic(&t->session,t->reliable_out,t->telemetry_writer_id,(uint8_t*)data,(size_t)len);
    const bool marked=fair_v1_slot_mark_send_result(slot,t_send_us,queued);
    if (queued) uxr_flash_output_streams(&t->session);
    xSemaphoreGive(t->session_mutex);
    if (!marked) return FAIR_DDS_ENQUEUE_ERR_SLOT_MARK_FAILED;
    return queued ? 0 : FAIR_DDS_ENQUEUE_ERR_STREAM_REJECTED;
}

void fair_dds_transport_stop(fair_dds_transport_t *t)
{
    if (!t) return;
    t->session_task_run=false;
    for (unsigned i=0;i<100U && t->session_task!=NULL;++i) vTaskDelay(pdMS_TO_TICKS(5));
    if (t->session_mutex && xSemaphoreTake(t->session_mutex,pdMS_TO_TICKS(1000))==pdTRUE){ close_session(t); xSemaphoreGive(t->session_mutex); }
    if (t->session_mutex){ vSemaphoreDelete(t->session_mutex); t->session_mutex=NULL; }
}
