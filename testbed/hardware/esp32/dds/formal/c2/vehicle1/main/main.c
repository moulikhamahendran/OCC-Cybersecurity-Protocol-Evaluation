#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include "esp_err.h"
#include "esp_log.h"
#include "fair_dds_profile.h"
#include "fair_dds_network.h"
#include "fair_dds_transport.h"
#include "fair_dds_benchmark.h"
static const char *TAG="FAIR_DDS_MAIN";
static bool pf(const char *s,float *o){ if(!s||!s[0]||!o)return false; errno=0; char *e=NULL; float v=strtof(s,&e); if(errno||e==s||!e||*e!='\0')return false; *o=v; return true; }
static bool workload(fair_dds_benchmark_config_t *c)
{
    if(!c||!CONFIG_FAIR_RUN_ID[0]||!CONFIG_FAIR_WORKLOAD_SPEED[0]||!CONFIG_FAIR_WORKLOAD_POS_X[0]||!CONFIG_FAIR_WORKLOAD_POS_Y[0]||!CONFIG_FAIR_WORKLOAD_HEADING[0]||!CONFIG_FAIR_WORKLOAD_BATTERY_PCT[0]||!CONFIG_FAIR_WORKLOAD_STATE[0]) return false;
    c->run_id=CONFIG_FAIR_RUN_ID; c->profile_name=FAIR_DDS_PROFILE_NAME; c->repeat_index=CONFIG_FAIR_REPEAT_INDEX; c->serial_number="VM-001"; c->state=CONFIG_FAIR_WORKLOAD_STATE;
    return pf(CONFIG_FAIR_WORKLOAD_SPEED,&c->speed)&&pf(CONFIG_FAIR_WORKLOAD_POS_X,&c->pos_x)&&pf(CONFIG_FAIR_WORKLOAD_POS_Y,&c->pos_y)&&pf(CONFIG_FAIR_WORKLOAD_HEADING,&c->heading)&&pf(CONFIG_FAIR_WORKLOAD_BATTERY_PCT,&c->battery_pct);
}
void app_main(void)
{
    if(!CONFIG_FAIR_WIFI_SSID[0]||!CONFIG_FAIR_DDS_AGENT_IP[0]){ ESP_LOGW(TAG,"%s compile-only state",FAIR_DDS_PROFILE_NAME); return; }
    fair_dds_benchmark_config_t cfg={0};
    if(!workload(&cfg)){ ESP_LOGW(TAG,"FAIR workload not configured; refusing runtime"); return; }
    esp_err_t err=fair_dds_network_connect(CONFIG_FAIR_WIFI_SSID,CONFIG_FAIR_WIFI_PASSWORD,pdMS_TO_TICKS(30000));
    if(err!=ESP_OK){ ESP_LOGE(TAG,"Wi-Fi failed: %s",esp_err_to_name(err)); return; }
    fair_dds_transport_t t;
    if(!fair_dds_transport_init(&t,CONFIG_FAIR_DDS_AGENT_IP,CONFIG_FAIR_DDS_AGENT_PORT,"VM-001",FAIR_DDS_SECURITY_LEVEL)){ ESP_LOGE(TAG,"transport init failed"); return; }
    if(!fair_dds_transport_start(&t)){ ESP_LOGE(TAG,"XRCE startup failed"); fair_dds_transport_stop(&t); return; }
    err=fair_dds_benchmark_run(&t,&cfg);
    if(err!=ESP_OK) ESP_LOGE(TAG,"benchmark failed: %s",esp_err_to_name(err));
    fair_dds_transport_stop(&t);
}
