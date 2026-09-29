#!/usr/bin/env bash
set -euo pipefail

CONTAINER_SECURITY_DIR="/workspace/testbed/config/dds/security"
OUTPUT_DIR="$CONTAINER_SECURITY_DIR/container"
PLUGIN_DIR="/opt/cyclonedds/lib"

required_files=(
  "$CONTAINER_SECURITY_DIR/identity_ca_cert.pem"
  "$CONTAINER_SECURITY_DIR/permissions_ca_cert.pem"
  "$CONTAINER_SECURITY_DIR/governance_c1.p7s"
  "$CONTAINER_SECURITY_DIR/governance_c2.p7s"
  "$CONTAINER_SECURITY_DIR/permissions_publisher.p7s"
  "$CONTAINER_SECURITY_DIR/permissions_subscriber.p7s"
  "$CONTAINER_SECURITY_DIR/publisher_cert.pem"
  "$CONTAINER_SECURITY_DIR/subscriber_cert.pem"
  "$CONTAINER_SECURITY_DIR/private/publisher_key.pem"
  "$CONTAINER_SECURITY_DIR/private/subscriber_key.pem"
  "$PLUGIN_DIR/libdds_security_auth.so"
  "$PLUGIN_DIR/libdds_security_ac.so"
  "$PLUGIN_DIR/libdds_security_crypto.so"
)

for required_file in "${required_files[@]}"; do
  if [[ ! -f "$required_file" ]]; then
    echo "Missing required file: $required_file"
    exit 1
  fi
done

mkdir -p "$OUTPUT_DIR"

create_config() {
  local profile="$1"
  local identity="$2"

  cat > "$OUTPUT_DIR/${profile}_${identity}.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<CycloneDDS>
  <Domain id="any">
    <Security>
      <Authentication>
        <Library
          initFunction="init_authentication"
          finalizeFunction="finalize_authentication"
          path="$PLUGIN_DIR/libdds_security_auth.so"/>
        <IdentityCA>file:$CONTAINER_SECURITY_DIR/identity_ca_cert.pem</IdentityCA>
        <IdentityCertificate>file:$CONTAINER_SECURITY_DIR/${identity}_cert.pem</IdentityCertificate>
        <PrivateKey>file:$CONTAINER_SECURITY_DIR/private/${identity}_key.pem</PrivateKey>
      </Authentication>

      <Cryptographic>
        <Library
          initFunction="init_crypto"
          finalizeFunction="finalize_crypto"
          path="$PLUGIN_DIR/libdds_security_crypto.so"/>
      </Cryptographic>

      <AccessControl>
        <Library
          initFunction="init_access_control"
          finalizeFunction="finalize_access_control"
          path="$PLUGIN_DIR/libdds_security_ac.so"/>
        <PermissionsCA>file:$CONTAINER_SECURITY_DIR/permissions_ca_cert.pem</PermissionsCA>
        <Governance>file:$CONTAINER_SECURITY_DIR/governance_${profile}.p7s</Governance>
        <Permissions>file:$CONTAINER_SECURITY_DIR/permissions_${identity}.p7s</Permissions>
      </AccessControl>
    </Security>
  </Domain>
</CycloneDDS>
EOF
}

create_config c1 publisher
create_config c1 subscriber
create_config c2 publisher
create_config c2 subscriber

echo "DDS Linux container configurations generated"

for config in "$OUTPUT_DIR"/c[12]_{publisher,subscriber}.xml; do
  echo "$config"
done
