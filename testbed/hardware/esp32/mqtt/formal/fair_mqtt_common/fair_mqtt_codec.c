#include <stdint.h>
#include <string.h>

#include "cJSON.h"

#include "fair_mqtt_codec.h"

bool fair_mqtt_encode_payload(
    const fair_v1_payload_t *payload,
    char *output,
    size_t output_size,
    size_t *output_len
)
{
    if (
        payload == NULL ||
        output == NULL ||
        output_size == 0U ||
        output_len == NULL ||
        payload->schema_ver == NULL ||
        payload->serialNumber == NULL ||
        payload->state == NULL ||
        strcmp(
            payload->schema_ver,
            FAIR_V1_PAYLOAD_SCHEMA_VERSION
        ) != 0 ||
        !fair_v1_seq_valid(payload->seq)
    ) {
        return false;
    }

    cJSON *root =
        cJSON_CreateObject();

    if (root == NULL) {
        return false;
    }

    bool ok = true;

    ok =
        ok &&
        cJSON_AddStringToObject(
            root,
            "schema_ver",
            payload->schema_ver
        ) != NULL;

    ok =
        ok &&
        cJSON_AddStringToObject(
            root,
            "serialNumber",
            payload->serialNumber
        ) != NULL;

    ok =
        ok &&
        cJSON_AddNumberToObject(
            root,
            "seq",
            (double)payload->seq
        ) != NULL;

    ok =
        ok &&
        cJSON_AddNumberToObject(
            root,
            "t_sched_us",
            (double)payload->t_sched_us
        ) != NULL;

    ok =
        ok &&
        cJSON_AddNumberToObject(
            root,
            "speed",
            (double)payload->speed
        ) != NULL;

    ok =
        ok &&
        cJSON_AddNumberToObject(
            root,
            "pos_x",
            (double)payload->pos_x
        ) != NULL;

    ok =
        ok &&
        cJSON_AddNumberToObject(
            root,
            "pos_y",
            (double)payload->pos_y
        ) != NULL;

    ok =
        ok &&
        cJSON_AddNumberToObject(
            root,
            "heading",
            (double)payload->heading
        ) != NULL;

    ok =
        ok &&
        cJSON_AddNumberToObject(
            root,
            "battery_pct",
            (double)payload->battery_pct
        ) != NULL;

    ok =
        ok &&
        cJSON_AddStringToObject(
            root,
            "state",
            payload->state
        ) != NULL;

    if (!ok) {
        cJSON_Delete(root);
        return false;
    }

    char *encoded =
        cJSON_PrintUnformatted(root);

    cJSON_Delete(root);

    if (encoded == NULL) {
        return false;
    }

    const size_t encoded_len =
        strlen(encoded);

    if (
        encoded_len + 1U >
        output_size
    ) {
        cJSON_free(encoded);
        return false;
    }

    memcpy(
        output,
        encoded,
        encoded_len + 1U
    );

    cJSON_free(encoded);

    *output_len =
        encoded_len;

    return true;
}

bool fair_mqtt_decode_echo(
    const char *json,
    size_t json_len,
    const char *expected_serial_number,
    uint32_t *seq_out
)
{
    if (
        json == NULL ||
        json_len == 0U ||
        expected_serial_number == NULL ||
        seq_out == NULL
    ) {
        return false;
    }

    if (
        memchr(
            json,
            '\0',
            json_len
        ) != NULL
    ) {
        return false;
    }

    cJSON *root =
        cJSON_Parse(json);

    if (
        root == NULL ||
        !cJSON_IsObject(root)
    ) {
        cJSON_Delete(root);
        return false;
    }

    if (
        cJSON_GetArraySize(root) != 2
    ) {
        cJSON_Delete(root);
        return false;
    }

    const cJSON *serial =
        cJSON_GetObjectItemCaseSensitive(
            root,
            "serialNumber"
        );

    const cJSON *seq =
        cJSON_GetObjectItemCaseSensitive(
            root,
            "seq"
        );

    if (
        !cJSON_IsString(serial) ||
        serial->valuestring == NULL ||
        !cJSON_IsNumber(seq)
    ) {
        cJSON_Delete(root);
        return false;
    }

    if (
        strcmp(
            serial->valuestring,
            expected_serial_number
        ) != 0
    ) {
        cJSON_Delete(root);
        return false;
    }

    const double seq_value =
        seq->valuedouble;

    if (
        seq_value < 0.0 ||
        seq_value >
            (double)FAIR_V1_LAST_SEQ
    ) {
        cJSON_Delete(root);
        return false;
    }

    const uint32_t parsed_seq =
        (uint32_t)seq_value;

    if (
        (double)parsed_seq !=
        seq_value
    ) {
        cJSON_Delete(root);
        return false;
    }

    if (
        !fair_v1_seq_valid(
            parsed_seq
        )
    ) {
        cJSON_Delete(root);
        return false;
    }

    *seq_out =
        parsed_seq;

    cJSON_Delete(root);

    return true;
}
