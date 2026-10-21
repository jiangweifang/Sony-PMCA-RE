#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
module="$root/qemu"
patch="$root/modules/qemu-j1.patch"
expected=e43c4d0f66698db7640a80d7a680af5ac5e0291a

[[ -f "$patch" ]] || { echo "Missing local patch: $patch" >&2; exit 2; }
actual="$(git -C "$module" rev-parse HEAD)"
[[ "$actual" == "$expected" ]] || {
  echo "Wrong QEMU submodule revision: $actual; expected $expected" >&2
  exit 2
}
if git -c core.autocrlf=false -C "$module" apply --reverse --check "$patch" >/dev/null 2>&1; then
  echo 'CX89700_J1 patch is already applied; no files changed.'
else
  git -c core.autocrlf=false -C "$module" apply --check "$patch"
  git -c core.autocrlf=false -C "$module" apply "$patch"
  echo 'Applied the local CX89700_J1 patch. No camera access or remote writes.'
fi
