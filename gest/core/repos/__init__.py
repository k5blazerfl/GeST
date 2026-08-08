"""Software repositories (overlays) module core.

Lists enabled repositories from /etc/portage/repos.conf (fast, no network);
mutations run `eselect repository` through the polkit-gated backend. Pure
parsing/validation is CI-testable.
"""
