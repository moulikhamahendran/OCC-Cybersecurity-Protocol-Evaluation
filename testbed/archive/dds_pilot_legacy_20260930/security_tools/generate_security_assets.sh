#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

SECURITY_DIR="$SCRIPT_DIR/security"
PRIVATE_DIR="$SECURITY_DIR/private"
OPENSSL_BIN="$(brew --prefix openssl)/bin/openssl"

mkdir -p "$SECURITY_DIR" "$PRIVATE_DIR"

if [[ -n "$(find "$SECURITY_DIR" -type f -print -quit)" ]]; then
  echo "Security directory is not empty:"
  echo "$SECURITY_DIR"
  echo "Remove existing generated assets before regenerating."
  exit 1
fi

echo "Generating DDS identity CA"

"$OPENSSL_BIN" req \
  -x509 \
  -newkey rsa:2048 \
  -sha256 \
  -nodes \
  -days 3650 \
  -subj "/C=DE/ST=Saxony-Anhalt/L=Magdeburg/O=OvGU-IEPS/OU=OCC-Testbed/CN=OCC-DDS-Identity-CA" \
  -keyout "$PRIVATE_DIR/identity_ca_key.pem" \
  -out "$SECURITY_DIR/identity_ca_cert.pem"

echo "Generating DDS permissions CA"

"$OPENSSL_BIN" req \
  -x509 \
  -newkey rsa:2048 \
  -sha256 \
  -nodes \
  -days 3650 \
  -subj "/C=DE/ST=Saxony-Anhalt/L=Magdeburg/O=OvGU-IEPS/OU=OCC-Testbed/CN=OCC-DDS-Permissions-CA" \
  -keyout "$PRIVATE_DIR/permissions_ca_key.pem" \
  -out "$SECURITY_DIR/permissions_ca_cert.pem"

generate_identity() {
  local identity="$1"
  local common_name="$2"

  "$OPENSSL_BIN" req \
    -newkey rsa:2048 \
    -sha256 \
    -nodes \
    -subj "/C=DE/ST=Saxony-Anhalt/L=Magdeburg/O=OvGU-IEPS/OU=OCC-Testbed/CN=$common_name" \
    -keyout "$PRIVATE_DIR/${identity}_key.pem" \
    -out "$PRIVATE_DIR/${identity}.csr"

  "$OPENSSL_BIN" x509 \
    -req \
    -in "$PRIVATE_DIR/${identity}.csr" \
    -CA "$SECURITY_DIR/identity_ca_cert.pem" \
    -CAkey "$PRIVATE_DIR/identity_ca_key.pem" \
    -CAcreateserial \
    -days 3650 \
    -sha256 \
    -out "$SECURITY_DIR/${identity}_cert.pem"
}

generate_identity "publisher" "DDS-Publisher"
generate_identity "subscriber" "DDS-Subscriber"

PUBLISHER_SUBJECT="$(
  "$OPENSSL_BIN" x509 \
    -in "$SECURITY_DIR/publisher_cert.pem" \
    -noout \
    -subject \
    -nameopt RFC2253 |
  sed 's/^subject=//'
)"

SUBSCRIBER_SUBJECT="$(
  "$OPENSSL_BIN" x509 \
    -in "$SECURITY_DIR/subscriber_cert.pem" \
    -noout \
    -subject \
    -nameopt RFC2253 |
  sed 's/^subject=//'
)"

create_governance() {
  local profile="$1"
  local protection="$2"

  cat > "$SECURITY_DIR/governance_${profile}.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<dds xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:noNamespaceSchemaLocation="https://www.omg.org/spec/DDS-SECURITY/20170901/omg_shared_ca_governance.xsd">
  <domain_access_rules>
    <domain_rule>
      <domains>
        <id>0</id>
      </domains>
      <allow_unauthenticated_participants>false</allow_unauthenticated_participants>
      <enable_join_access_control>true</enable_join_access_control>
      <discovery_protection_kind>${protection}</discovery_protection_kind>
      <liveliness_protection_kind>${protection}</liveliness_protection_kind>
      <rtps_protection_kind>${protection}</rtps_protection_kind>
      <topic_access_rules>
        <topic_rule>
          <topic_expression>OCCVehicleState</topic_expression>
          <enable_discovery_protection>true</enable_discovery_protection>
          <enable_liveliness_protection>true</enable_liveliness_protection>
          <enable_read_access_control>true</enable_read_access_control>
          <enable_write_access_control>true</enable_write_access_control>
          <metadata_protection_kind>${protection}</metadata_protection_kind>
          <data_protection_kind>${protection}</data_protection_kind>
        </topic_rule>
      </topic_access_rules>
    </domain_rule>
  </domain_access_rules>
</dds>
EOF
}

create_permissions() {
  local identity="$1"
  local subject="$2"
  local operation="$3"

  cat > "$SECURITY_DIR/permissions_${identity}.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<dds xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:noNamespaceSchemaLocation="https://www.omg.org/spec/DDS-SECURITY/20170901/omg_shared_ca_permissions.xsd">
  <permissions>
    <grant name="${identity}_permissions">
      <subject_name>${subject}</subject_name>
      <validity>
        <not_before>2026-01-01T00:00:00</not_before>
        <not_after>2036-01-01T00:00:00</not_after>
      </validity>
      <allow_rule>
        <domains>
          <id>0</id>
        </domains>
        <${operation}>
          <topics>
            <topic>OCCVehicleState</topic>
          </topics>
          <partitions>
            <partition>*</partition>
          </partitions>
        </${operation}>
      </allow_rule>
      <default>DENY</default>
    </grant>
  </permissions>
</dds>
EOF
}

sign_document() {
  local input="$1"
  local output="$2"

  "$OPENSSL_BIN" smime \
    -sign \
    -in "$input" \
    -text \
    -out "$output" \
    -signer "$SECURITY_DIR/permissions_ca_cert.pem" \
    -inkey "$PRIVATE_DIR/permissions_ca_key.pem"
}

create_governance "c1" "SIGN"
create_governance "c2" "ENCRYPT"

create_permissions \
  "publisher" \
  "$PUBLISHER_SUBJECT" \
  "publish"

create_permissions \
  "subscriber" \
  "$SUBSCRIBER_SUBJECT" \
  "subscribe"

sign_document \
  "$SECURITY_DIR/governance_c1.xml" \
  "$SECURITY_DIR/governance_c1.p7s"

sign_document \
  "$SECURITY_DIR/governance_c2.xml" \
  "$SECURITY_DIR/governance_c2.p7s"

sign_document \
  "$SECURITY_DIR/permissions_publisher.xml" \
  "$SECURITY_DIR/permissions_publisher.p7s"

sign_document \
  "$SECURITY_DIR/permissions_subscriber.xml" \
  "$SECURITY_DIR/permissions_subscriber.p7s"

chmod 600 "$PRIVATE_DIR"/*.pem
rm -f "$PRIVATE_DIR"/*.csr
rm -f "$SECURITY_DIR"/*.srl

echo
echo "DDS Security assets generated"
echo "Publisher subject: $PUBLISHER_SUBJECT"
echo "Subscriber subject: $SUBSCRIBER_SUBJECT"
