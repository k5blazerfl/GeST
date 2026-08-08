"""System settings module core (hostname / timezone / locale).

Reading current values is unprivileged; writing them goes through the polkit-
gated System backend. Pure and dependency-free, so it is unit-testable on CI.
"""
