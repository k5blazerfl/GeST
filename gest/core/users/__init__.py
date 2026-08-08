"""Users & Groups module core (frontend-agnostic).

Reading /etc/passwd and /etc/group is unprivileged; mutations go through the
polkit-gated backend (useradd/usermod/userdel/groupadd/groupdel). Nothing here
imports a toolkit, so it is unit-testable on CI.
"""
