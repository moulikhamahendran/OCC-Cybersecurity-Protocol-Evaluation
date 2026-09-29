#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

SECURITY_DIR="$SCRIPT_DIR/security"
PRIVATE_DIR="$SECURITY_DIR/private"

DDS_HOME="${CYCLONEDDS_HOME:-/Users/moulikham/.local/cyclonedds-11.0.1-security}"
PLUGIN_DIR="$DDS_HOME/lib"

required_files=(
  "$SECURITY_DIR/identity_ca_cert.pem"
  "$SECURITY_DIR/permissions_ca_cert.pem"
  "$SECURITY_DIR/governance_c1.p7s"
  "$SECURITY_DIR/governance_c2.p7s"
  "$SECURITY_DIR/permissions_publisher.p7s"
  "$SECURITY_DIR/permissions_subscriber.p7s"
  "$SECURITY_DIR/publisher_cert.pem"
  "$SECURITY_DIR/subscriber_cert.pem"
  "$PRIVATE_DIR/publisher_key.pem"
  "$PRIVATE_DIR/subscriber_key.pem"
  "$PLUGIN_DIR/libdds_security_auth.dylib"
  "$PLUGIN_DIR/libdds_security_ac.dylib"
  "$PLUGIN_DIR/libdds_security_crypto.dylib"
)

for required_file in "${required_files[@]}"; do
  if [[ ! -f "$required_file" ]]; then
    echo "Missing required file: $required_file"
    exit 1
  fi
done

create_config() {
  local profile="$1"
  local identity="$2"

  cat > "$SECURITY_DIR/${profile}_${identity}.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<CycloneDDS>
  <Domain id="any">
    <Security>
      <Authentication>
        <Library
          initFunction="init_authentication"
          finalizeFunction="finalize_authentication"
          path="$PLUGIN_DIR/libdds_security_auth.dylib"/>
        <IdentityCA>file:$SECURITY_DIR/identity_ca_cert.pem</IdentityCA>
        <IdentityCertificate>file:$SECURITY_DIR/${identity}_cert.pem</IdentityCertificate>
        <PrivateKey>file:$PRIVATE_DIR/${identity}_key.pem</PrivateKey>
      </Authentication>

      <Cryptographic>
        <Library
          initFunction="init_crypto"
          finalizeFunction="finalize_crypto"
          path="$PLUGIN_DIR/libdds_security_crypto.dylib"/>
      </Cryptographic>

      <AccessControl>
        <Library
          initFunction="init_access_control"
          finalizeFunction="finalize_access_control"
          path="$PLUGIN_DIR/libdds_security_ac.dylib"/>
        <PermissionsCA>file:$SECURITY_DIR/permissions_ca_cert.pem</PermissionsCA>
        <Governance>file:$SECURITY_DIR/governance_${profile}.p7s</Governance>
        <Permissions>file:$SECURITY_DIR/permissions_${identity}.p7s</Permissions>
      </AccessControl>
    </Security>
  </Domain>
</CycloneDDS>
EOF
}

create_config "c1" "publisher"
create_config "c1" "subscriber"
create_config "c2" "publisher"
create_config "c2" "subscriber"

echo "DDS runtime configurations generated"

for config in "$SECURITY_DIR"/c[12]_{publisher,subscriber}.xml; do
  echo "$config"
done
