#!/usr/bin/env bash
# Open TCP 80 and 443 to the internet on the voice host's security group.
#
# Scope is deliberately narrow: this instance, this group, these two ports,
# IPv4 only. Port 22 and every other rule are left untouched. Idempotent:
# rules that already exist are reported and skipped.
#
# Run as the ubuntu user with the already-authenticated AWS CLI:
#     scripts/deploy/open-ports.sh
#
# Source for the API shape:
#   https://docs.aws.amazon.com/cli/latest/reference/ec2/authorize-security-group-ingress.html
set -euo pipefail

REGION="ap-south-1"
INSTANCE_ID="i-0c645ae0bd6a0522d"
EXPECTED_GROUP="sg-0ae5a8799482e1588"
CIDR="0.0.0.0/0"
PORTS=(80 443)

say() { printf '%s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

command -v aws >/dev/null || fail "aws CLI not found"

# 1. Verify the instance and the group before touching anything.
say "== verifying instance ${INSTANCE_ID} =="
GROUP_ID="$(aws ec2 describe-instances \
    --region "${REGION}" \
    --instance-ids "${INSTANCE_ID}" \
    --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' \
    --output text)"
[[ "${GROUP_ID}" == "${EXPECTED_GROUP}" ]] \
    || fail "instance group is ${GROUP_ID}, expected ${EXPECTED_GROUP}"
say "group ${GROUP_ID} confirmed"

# 2. Snapshot the rules.
describe() {
    aws ec2 describe-security-groups \
        --region "${REGION}" \
        --group-ids "${GROUP_ID}" \
        --output json
}
BEFORE="$(describe)"
printf '%s\n' "${BEFORE}" > /tmp/gnani-sg-before.json
say "== rules before =="
python3 - "${BEFORE}" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
for group in data["SecurityGroups"]:
    for perm in group["IpPermissions"]:
        for rng in perm.get("IpRanges", []):
            print(f"  {perm.get('IpProtocol')} {perm.get('FromPort')}-{perm.get('ToPort')} {rng.get('CidrIp')}")
PY

# 3. Authorise only what is missing.
for port in "${PORTS[@]}"; do
    EXISTS="$(python3 - "${BEFORE}" "${port}" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
port = int(sys.argv[2])
for group in data["SecurityGroups"]:
    for perm in group["IpPermissions"]:
        if (perm.get("IpProtocol") in ("tcp", "-1")
                and perm.get("FromPort", port) <= port <= perm.get("ToPort", port)):
            for rng in perm.get("IpRanges", []):
                if rng.get("CidrIp") == "0.0.0.0/0":
                    print("yes")
                    raise SystemExit
print("no")
PY
)"
    if [[ "${EXISTS}" == "yes" ]]; then
        say "  tcp/${port} from ${CIDR}: already open, skipped"
    else
        say "  tcp/${port} from ${CIDR}: authorising"
        aws ec2 authorize-security-group-ingress \
            --region "${REGION}" \
            --group-id "${GROUP_ID}" \
            --ip-permissions "IpProtocol=tcp,FromPort=${port},ToPort=${port},IpRanges=[{CidrIp=${CIDR}}]" \
            --output json >/dev/null
    fi
done

# 4. Snapshot again and show the diff.
AFTER="$(describe)"
printf '%s\n' "${AFTER}" > /tmp/gnani-sg-after.json
say "== rules after =="
python3 - "${AFTER}" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
for group in data["SecurityGroups"]:
    for perm in group["IpPermissions"]:
        for rng in perm.get("IpRanges", []):
            print(f"  {perm.get('IpProtocol')} {perm.get('FromPort')}-{perm.get('ToPort')} {rng.get('CidrIp')}")
PY

say "== diff (before -> after) =="
python3 - "${BEFORE}" "${AFTER}" <<'PY'
import json, sys

def rules(raw):
    out = set()
    for group in json.loads(raw)["SecurityGroups"]:
        for perm in group["IpPermissions"]:
            for rng in perm.get("IpRanges", []):
                out.add((perm.get("IpProtocol"), perm.get("FromPort"),
                         perm.get("ToPort"), rng.get("CidrIp")))
    return out

before, after = rules(sys.argv[1]), rules(sys.argv[2])
for rule in sorted(after - before, key=str):
    print(f"  + {rule}")
for rule in sorted(before - after, key=str):
    print(f"  - {rule}")
if before == after:
    print("  (no change)")
PY
say "OPEN PORTS OK"
