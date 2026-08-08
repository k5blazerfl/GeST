"""make.conf editor core: parse /etc/portage/make.conf and render edits.

Reads are unprivileged; writing goes through the polkit-gated backend
(software.modify-config). Pure parsing/rendering — preserves the rest of the
file, ${...} references, and comments — so it is CI-testable.
"""
