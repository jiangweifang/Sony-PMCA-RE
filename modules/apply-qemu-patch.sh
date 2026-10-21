#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
module="$root/qemu"
profile=report/2026-10-17-qemu-native-camera/runtime/analysis/prepare-assets.py

[[ -e "$module/.git" ]] || {
  echo 'QEMU submodule is not initialized; run git submodule update --init -- qemu.' >&2
  exit 2
}
record="$(git -C "$root" ls-files --stage -- qemu)"
[[ -n "$record" && "$record" != *$'\n'* ]] || {
  echo 'Expected one resolved QEMU gitlink in the parent index.' >&2
  exit 2
}
read -r mode expected stage path <<< "$record"
[[ "$mode" == 160000 && "$stage" == 0 && "$path" == qemu ]] || {
  echo 'QEMU is not a resolved submodule in the parent index.' >&2
  exit 2
}
actual="$(git -C "$module" rev-parse HEAD)"
[[ "$actual" == "$expected" ]] || {
  echo "Wrong QEMU submodule revision: $actual; expected $expected" >&2
  exit 2
}
if ! git -C "$module" grep -q -G -e "^PRESET = 'CX89700_J1'$" "$actual" -- "$profile"; then
  echo 'The recorded QEMU commit does not contain the CX89700_J1 profile.' >&2
  exit 2
fi
echo "CX89700_J1 is already committed in the fork: $actual"
echo 'Checkout matches the parent gitlink. No patch was applied and no files were changed.'
