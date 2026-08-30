#!/usr/bin/env bash
# 放行 bubblewrap 创建 unprivileged user namespaces（Ubuntu 23.10+ 默认被 AppArmor 拦截）。
# 幂等：重复执行安全。需要 sudo。
#
# 原理：安装一条只针对 /usr/bin/bwrap 的 AppArmor profile（userns 规则），
# 不关闭全局 apparmor_restrict_unprivileged_userns，也不给 bwrap setuid。
set -euo pipefail

PROFILE_PATH="/etc/apparmor.d/bwrap-userns"

if [ "$(id -u)" -ne 0 ]; then
  echo "需要 root 权限，请使用 sudo 运行：sudo bash $0" >&2
  exit 1
fi

if ! command -v bwrap >/dev/null 2>&1; then
  echo "未找到 bwrap，请先安装：sudo apt install bubblewrap" >&2
  exit 1
fi

cat > "$PROFILE_PATH" <<'EOF'
abi <abi/4.0>,
include <tunables/global>

# 放行 bubblewrap 创建 user namespace（deepagents-scaffold 沙箱执行需要）
/usr/bin/bwrap flags=(unconfined) {
  userns,
  include if exists <local/bwrap-userns>
}
EOF

apparmor_parser -r "$PROFILE_PATH"
echo "OK: AppArmor profile 已加载（$PROFILE_PATH），bwrap userns 已放行"

# 冒烟验证（以真实用户身份跑一次最小隔离命令）
SMOKE_USER="${SUDO_USER:-}"
if [ -n "$SMOKE_USER" ]; then
  if su - "$SMOKE_USER" -c "bwrap --unshare-all --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /bin /bin --ro-bind /lib64 /lib64 /bin/true" 2>/dev/null; then
    echo "OK: bwrap 冒烟验证通过"
  else
    echo "WARN: profile 已加载但冒烟验证失败，请检查内核版本与 AppArmor 状态" >&2
    exit 1
  fi
fi
